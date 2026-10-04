#!/usr/bin/env python3
"""Focused tests for the independent production Compose static contract."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "formal_release" / "check_static_production_contract.py"
COMPOSE_REL_PATH = "main/ops/docker-compose.production.yml"
ENV_REL_PATH = "main/backend/.env.production.example"
CHECKER_ID = "check_static_production_contract_live"


def _load_checker():
    spec = importlib.util.spec_from_file_location(CHECKER_ID, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def test_build_role_is_non_authoritative_and_rejects_ambiguity() -> None:
    from copy import deepcopy
    from typing import get_type_hints

    step = {"id": "canonical_backend", "with": {"tags": "example/backend:test"}}
    original = deepcopy(step)
    assert checker.build_role(step) == "backend"
    assert step == original
    assert checker.build_role({"name": "backend frontend", "with": {}}) is None
    assert checker.build_role({"name": "backend"}) is None
    assert checker.build_role({"name": "migration-runner", "with": {}}) == "migration-runner"
    annotation = get_type_hints(checker.build_role, include_extras=True)["return"]
    assert "kit:non-authoritative" in annotation.__metadata__[0]
    assert "fact_source=workflow_step_identity" in annotation.__metadata__[0]


def required_workflow(
    condition: str,
    *,
    step_name: str,
    uses: str | None = None,
    continue_on_error: bool | None = None,
) -> dict[str, Any]:
    step: dict[str, Any] = {
        "name": step_name,
        "if": condition,
        "uses": uses,
    }
    if uses is None:
        step.pop("uses")
        step["run"] = "echo contract"
    if continue_on_error is not None:
        step["continue-on-error"] = continue_on_error
    return {
        "jobs": {
            "docker-config-check": {
                "name": "docker-config-check",
                "steps": [step],
            }
        }
    }


GOOD_WORKFLOW = """
name: release-contract
concurrency:
  group: release-contract
  cancel-in-progress: false
jobs:
%s
"""

WORKFLOW_JOB = """
  %s:
    steps:
      - uses: actions/checkout@v4
"""

ARTIFACT_JOB = """
  artifact-metadata-check:
    steps:
      - id: canonical-builder
        uses: docker/setup-buildx-action@v3
        with:
          driver: docker-container
      - id: build-backend
        name: Build backend canonical role
        uses: docker/build-push-action@v6
        with:
          context: .
          builder: ${{ steps.canonical-builder.outputs.name }}
          file: main/backend/Dockerfile
          target: backend-runtime
          push: false
          provenance: true
          sbom: true
          no-cache: true
          platforms: linux/amd64
          build-args: SOURCE_DATE_EPOCH=0
          tags: mrw-local/canonical-backend:${{ github.sha }}
          outputs: type=oci,dest=immutable-release-metadata/backend/image.oci.tar
      - id: build-frontend
        name: Build frontend canonical role
        uses: docker/build-push-action@v6
        with:
          context: main/frontend-modern
          builder: ${{ steps.canonical-builder.outputs.name }}
          file: Dockerfile
          target: frontend-runtime
          push: false
          provenance: true
          sbom: true
          no-cache: true
          platforms: linux/amd64
          build-args: SOURCE_DATE_EPOCH=0
          tags: mrw-local/canonical-frontend:${{ github.sha }}
          outputs: type=oci,dest=immutable-release-metadata/frontend/image.oci.tar
      - id: build-migration-runner
        name: Build migration-runner canonical role
        uses: docker/build-push-action@v6
        with:
          context: .
          builder: ${{ steps.canonical-builder.outputs.name }}
          file: main/backend/Dockerfile
          target: migration-runner
          push: false
          provenance: true
          sbom: true
          no-cache: true
          platforms: linux/amd64
          build-args: SOURCE_DATE_EPOCH=0
          tags: mrw-local/canonical-migration-runner:${{ github.sha }}
          outputs: type=oci,dest=immutable-release-metadata/migration-runner/image.oci.tar
      - id: canonical-evidence
        name: Inspect canonical predicates and OCI contents
        env:
          BACKEND_DIGEST: ${{ steps.build-backend.outputs.digest }}
          FRONTEND_DIGEST: ${{ steps.build-frontend.outputs.digest }}
          MIGRATION_RUNNER_DIGEST: ${{ steps.build-migration-runner.outputs.digest }}
        run: |
          python3 - <<'PY'
          import os
          canonical = (os.environ["BACKEND_DIGEST"], os.environ["FRONTEND_DIGEST"], os.environ["MIGRATION_RUNNER_DIGEST"])
          paths = ("immutable-release-metadata/backend/", "immutable-release-metadata/frontend/", "immutable-release-metadata/migration-runner/")
          markers = ("https://slsa.dev/provenance/", "https://spdx.dev/Document", "predicateType", "spdxVersion", "subject_matches", "artifact_digest")
          errors = ("OCI root digest mismatch", "OCI blob digest mismatch", "canonical image platform is not linux/amd64", "canonical image manifest content is incomplete")
          files = ("digest-inspection.json", "provenance.intoto.json", "sbom.spdx.intoto.json")
          PY
      - id: rebuild-builder
        uses: docker/setup-buildx-action@v3
        with:
          driver: docker-container
      - id: rebuild-backend
        name: Clean rebuild backend role
        uses: docker/build-push-action@v6
        with:
          context: .
          builder: ${{ steps.rebuild-builder.outputs.name }}
          file: main/backend/Dockerfile
          target: backend-runtime
          push: false
          provenance: false
          sbom: false
          no-cache: true
          platforms: linux/amd64
          build-args: SOURCE_DATE_EPOCH=0
          tags: mrw-local/rebuild-backend:${{ github.sha }}
          outputs: type=oci,dest=rebuild-output/backend.oci.tar
      - id: rebuild-frontend
        name: Clean rebuild frontend role
        uses: docker/build-push-action@v6
        with:
          context: main/frontend-modern
          builder: ${{ steps.rebuild-builder.outputs.name }}
          file: Dockerfile
          target: frontend-runtime
          push: false
          provenance: false
          sbom: false
          no-cache: true
          platforms: linux/amd64
          build-args: SOURCE_DATE_EPOCH=0
          tags: mrw-local/rebuild-frontend:${{ github.sha }}
          outputs: type=oci,dest=rebuild-output/frontend.oci.tar
      - id: rebuild-migration-runner
        name: Clean rebuild migration-runner role
        uses: docker/build-push-action@v6
        with:
          context: .
          builder: ${{ steps.rebuild-builder.outputs.name }}
          file: main/backend/Dockerfile
          target: migration-runner
          push: false
          provenance: false
          sbom: false
          no-cache: true
          platforms: linux/amd64
          build-args: SOURCE_DATE_EPOCH=0
          tags: mrw-local/rebuild-migration-runner:${{ github.sha }}
          outputs: type=oci,dest=rebuild-output/migration-runner.oci.tar
      - name: Compare clean rebuild digests
        env:
          BACKEND_CANONICAL: ${{ steps.canonical-evidence.outputs.backend_digest }}
          BACKEND_REBUILD: ${{ steps.rebuild-backend.outputs.digest }}
          FRONTEND_CANONICAL: ${{ steps.canonical-evidence.outputs.frontend_digest }}
          FRONTEND_REBUILD: ${{ steps.rebuild-frontend.outputs.digest }}
          MIGRATION_RUNNER_CANONICAL: ${{ steps.canonical-evidence.outputs.migration_runner_digest }}
          MIGRATION_RUNNER_REBUILD: ${{ steps.rebuild-migration-runner.outputs.digest }}
        run: |
          python3 - <<'PY'
          receipt = {"status": "MATCH", "comparison_scope": "linux/amd64-image-manifest-digest", "builders": {"canonical": "canonical-builder", "rebuild": "rebuild-builder", "relationship": "separate-builder-instances"}}
          errors = ("non-reproducible clean build", "rebuild OCI blob digest mismatch")
          PY
      - name: Build authority and role metadata
        run: |
          python3 - <<'PY'
          ceiling = "PRODUCTION_RELEASE_NOT_AUTHORIZED"
          status = "UNEXECUTED_AUTHORITY_REQUIRED"
          authority = {"signing_status": status, "publishing_status": status, "receipt": "authority-receipt.json"}
          PY
      - uses: actions/upload-artifact@v4
        with:
          name: immutable-release-metadata
          path: immutable-release-metadata/
          if-no-files-found: error
"""

SECURITY_JOB = """
  security-check:
    steps:
      - uses: actions/checkout@v4
        with:
          repository: 123rrr4tttt/functorial-kit
          ref: 785ff25e201c9eae84c862e68e786bc975e7a800
          path: .ci/functorial-kit-source
          persist-credentials: false
      - run: bandit -q -r main/backend/app
      - run: |
          python scripts/formal_release/check_functorial_kit_dependency_audit.py \
            --requirements main/backend/requirements.txt \
            --pyproject pyproject.toml \
            --manifest tools/functorial-kit/consumer-gate.manifest.json \
            --source-checkout .ci/functorial-kit-source \
            --public-requirements "${RUNNER_TEMP}/mrw-public-pypi-requirements.txt" \
            --report "${RUNNER_TEMP}/mrw-functorial-kit-dependency-audit.json"
      - run: pip-audit -r "${RUNNER_TEMP}/mrw-public-pypi-requirements.txt" --strict
      - working-directory: main/frontend-modern
        run: pnpm install --frozen-lockfile
      - working-directory: main/frontend-modern
        run: pnpm audit --prod --audit-level high
      - uses: gitleaks/gitleaks-action@v2
"""

FRONTEND_COMPONENT_E2E_JOB = """
  frontend-component-e2e-check:
    steps:
      - working-directory: main/frontend-modern
        run: pnpm install --frozen-lockfile
      - working-directory: main/frontend-modern
        run: pnpm build-storybook
      - working-directory: main/frontend-modern
        run: pnpm exec playwright install --with-deps chromium
      - working-directory: main/frontend-modern
        run: pnpm test:e2e
"""

IMAGE_SCAN_JOB = """
  image-vulnerability-scan-check:
    needs: artifact-metadata-check
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: immutable-release-metadata
          path: immutable-release-metadata
      - name: Revalidate canonical scan input contents
        run: |
          python3 - <<'PY'
          markers = ("vulnerability-scan-evidence", "HIGH", "CRITICAL", "canonical_digest", "artifact_digest", "exit-code=1", "sha256")
          authority = ("PRODUCTION_RELEASE_NOT_AUTHORIZED", "UNEXECUTED_AUTHORITY_REQUIRED", "authority receipt hash mismatch")
          oci = ("OCI blob digest mismatch", "canonical image manifest digest mismatch")
          report = ("SchemaVersion", "ArtifactName", "Trivy report identity or schema mismatch")
          PY
      - name: Scan backend canonical OCI
        run: docker run --rm aquasec/trivy:0.67.2 image --input immutable-release-metadata/backend/image.oci.tar --exit-code 1 --severity HIGH,CRITICAL
      - name: Scan frontend canonical OCI
        run: docker run --rm aquasec/trivy:0.67.2 image --input immutable-release-metadata/frontend/image.oci.tar --exit-code 1 --severity HIGH,CRITICAL
      - name: Scan migration-runner canonical OCI
        run: docker run --rm aquasec/trivy:0.67.2 image --input immutable-release-metadata/migration-runner/image.oci.tar --exit-code 1 --severity HIGH,CRITICAL
      - name: Validate reports
        run: echo vulnerability-scan-evidence canonical_digest artifact_digest exit-code=1 sha256 SchemaVersion ArtifactName HIGH CRITICAL
      - uses: actions/upload-artifact@v4
        with:
          name: canonical-vulnerability-evidence
          path: vulnerability-scan-evidence/
          if-no-files-found: error
"""


def good_compose() -> str:
    return (
        textwrap.dedent(
            """
        services:
          db:
            image: "${DB_IMAGE_DIGEST:?required production sha256 digest}"
            environment:
              POSTGRES_USER: "${POSTGRES_USER:?required production database user}"
              POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?required production database password}"
          es:
            image: "${ES_IMAGE_DIGEST:?required production sha256 digest}"
            environment:
              xpack.security.enabled: "true"
          redis:
            image: "${REDIS_IMAGE_DIGEST:?required production sha256 digest}"
          backend:
            image: "${BACKEND_IMAGE_DIGEST:?required production sha256 digest}"
            environment:
              SERVICE_VERSION: 1.0.0
              DATABASE_URL: "${DATABASE_URL:?required production PostgreSQL URL}"
              ES_URL: "${ES_URL:?required production Elasticsearch URL}"
              REDIS_URL: "${REDIS_URL:?required production Redis URL}"
              RELEASE_BUILD_COMMIT: "${RELEASE_BUILD_COMMIT:?required production build commit}"
              RELEASE_BUILD_TREE: "${RELEASE_BUILD_TREE:?required production build tree}"
              RELEASE_BUILD_DIGEST: "${RELEASE_BUILD_DIGEST:?required production build digest}"
              RUN_MIGRATIONS: "${RUN_MIGRATIONS_BACKEND:?required backend migration policy}"
          celery-worker:
            image: "${BACKEND_IMAGE_DIGEST:?required production sha256 digest}"
            environment:
              SERVICE_VERSION: 1.0.0
              DATABASE_URL: "${DATABASE_URL:?required production PostgreSQL URL}"
              ES_URL: "${ES_URL:?required production Elasticsearch URL}"
              REDIS_URL: "${REDIS_URL:?required production Redis URL}"
              RELEASE_BUILD_COMMIT: "${RELEASE_BUILD_COMMIT:?required production build commit}"
              RELEASE_BUILD_TREE: "${RELEASE_BUILD_TREE:?required production build tree}"
              RELEASE_BUILD_DIGEST: "${RELEASE_BUILD_DIGEST:?required production build digest}"
              RUN_MIGRATIONS: "${RUN_MIGRATIONS_WORKER:?required worker migration policy}"
          frontend:
            image: "${FRONTEND_IMAGE_DIGEST:?required production sha256 digest}"
        volumes:
          db_data:
          es_data:
        """
        ).strip()
        + "\n"
    )


def good_workflow() -> str:
    simple = [
        category
        for category in checker.REQUIRED_CHECK_CATEGORIES
        if category
        not in {
            "security",
            "artifact-metadata",
            "frontend-component-e2e",
            "image-vulnerability-scan",
        }
    ]
    jobs = "".join(WORKFLOW_JOB % f"{category}-check" for category in simple)
    required_names = [f"{category}-check" for category in checker.REQUIRED_CHECK_CATEGORIES]
    needs_yaml = "".join(f"      - {name}\n" for name in required_names)
    convergence = f"""
  required-convergence-check:
    if: always()
    needs:
{needs_yaml}
    steps:
      - env:
          NEEDS_JSON: ${{{{ toJson(needs) }}}}
        run: |
          required = {tuple(required_names)!r}
          for job in required:
            result = needs[job]
            if result != "success":
              sys.exit(1)
"""
    return GOOD_WORKFLOW % (
        jobs + SECURITY_JOB + ARTIFACT_JOB + FRONTEND_COMPONENT_E2E_JOB + IMAGE_SCAN_JOB + convergence
    )


def test_yaml_sequence_comments_are_ignored_and_quoted_hash_is_scalar() -> None:
    text = """
services:
  x:
    command:
      - before # trailing comment
      # A standalone comment is not a sequence item.
      - 'value # not a comment'
"""

    parsed = checker.StrictYamlParser(text).parse()

    assert parsed == {
        "services": {
            "x": {"command": ["before", "value # not a comment"]},
        }
    }


def test_yaml_sequence_mixed_mapping_item_remains_rejected() -> None:
    text = "services:\n  x:\n    command:\n      - before\n      command: mixed\n"

    try:
        checker.StrictYamlParser(text).parse()
    except checker.StrictParseError as error:
        assert str(error) == "mixed_mapping_and_sequence"
    else:
        raise AssertionError("mixed sequence item must remain rejected")


class StaticProductionContractTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="s1-r3-static-")
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)

    def write_text(self, rel_path: str, content: str) -> None:
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_good_repo(self, compose: str | None = None) -> None:
        self.write_text(COMPOSE_REL_PATH, good_compose() if compose is None else compose)
        self.write_text(ENV_REL_PATH, "POSTGRES_USER=production_owner\nPOSTGRES_PASSWORD=production_password\n")
        self.write_text("pyproject.toml", '[project]\nversion = "1.0.0"\n')
        self.write_text("main/frontend-modern/package.json", '{"version": "1.0.0"}\n')
        self.write_text(".github/workflows/backend-tests.yml", good_workflow())
        contracts = {
            category: {
                "required_check": f"{category}-check",
                "source": ".github/workflows/backend-tests.yml",
            }
            for category in checker.REQUIRED_CHECK_CATEGORIES
        }
        self.write_text(
            ".github/branch-protection-required-checks.json",
            json.dumps(
                {
                    "branch": "main",
                    "required_checks": [f"{category}-check" for category in checker.REQUIRED_CHECK_CATEGORIES],
                    "required_check_contracts": contracts,
                    "required_check_sources": {
                        f"{category}-check": ".github/workflows/backend-tests.yml"
                        for category in checker.REQUIRED_CHECK_CATEGORIES
                    },
                }
            ),
        )

    def findings(self) -> dict[str, checker.Finding]:
        report = checker.evaluate_static_production_contract(self.root)
        return {finding.check_id: finding for finding in report.findings}

    def assert_finding(self, findings: dict[str, checker.Finding], check_id: str, status: str, evidence: str) -> None:
        finding = findings[check_id]
        self.assertEqual(status, finding.status, (finding.status, finding.summary, finding.evidence))
        self.assertTrue(any(evidence in item for item in finding.evidence), finding.evidence)

    def test_live_production_contract_passes_compose_family(self) -> None:
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
        self.assertEqual({}, failures)

    def test_production_contract_resolves_exact_service_set(self) -> None:
        self.write_good_repo()
        finding = self.findings()["compose.production_profile"]
        self.assertEqual("PASS", finding.status)
        self.assertIn("services=backend,celery-worker,db,es,frontend,redis", finding.evidence[0])

    def test_all_images_must_use_exact_fail_fast_digest_form(self) -> None:
        self.write_good_repo()
        states = checker.production_image_digest_states(checker.load_inputs(self.root))[0]
        self.assertEqual(
            {name: "required_reference" for name in checker.REQUIRED_PRODUCTION_SERVICES},
            states,
        )

        invalid = "ghcr.io/example/backend:1.0.0@sha256:" + "3" * 64
        self.write_good_repo(
            good_compose().replace("${BACKEND_IMAGE_DIGEST:?required production sha256 digest}", invalid)
        )
        self.assert_finding(self.findings(), "compose.image_digest_pinning", "FAIL", "backend.image=")

    def test_production_policy_requires_release_and_migration_bindings(self) -> None:
        self.write_good_repo()
        compose = good_compose().replace(
            '      RELEASE_BUILD_TREE: "${RELEASE_BUILD_TREE:?required production build tree}"\n',
            "",
        )
        self.write_text(COMPOSE_REL_PATH, compose)
        self.assert_finding(
            self.findings(),
            "compose.production_policy",
            "FAIL",
            "backend.RELEASE_BUILD_TREE=required_value_invalid",
        )

        self.write_good_repo()
        compose = good_compose().replace(
            "  backend:\n",
            "  backend:\n    build:\n      context: ../backend\n",
        )
        self.write_text(COMPOSE_REL_PATH, compose)
        self.assert_finding(self.findings(), "compose.production_policy", "FAIL", "backend.build=forbidden")

    def test_db_es_redis_ports_and_source_binds_fail_closed(self) -> None:
        self.write_good_repo()
        compose = good_compose().replace(
            'POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?required production database password}"\n',
            'POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?required production database password}"\n'
            '    ports:\n      - "5432:5432"\n',
        )
        self.write_text(COMPOSE_REL_PATH, compose)
        self.assert_finding(self.findings(), "compose.public_ports", "FAIL", "db.ports='5432:5432'")

        self.write_good_repo()
        compose = good_compose().replace(
            "  backend:\n",
            "  backend:\n    volumes:\n      - ../backend:/app\n",
        )
        self.write_text(COMPOSE_REL_PATH, compose)
        self.assert_finding(self.findings(), "compose.source_bind_mounts", "FAIL", "../backend:/app")

    def test_default_credentials_and_disabled_es_security_fail(self) -> None:
        self.write_good_repo()
        self.write_text(
            ENV_REL_PATH,
            "DATABASE_URL='postgresql+psycopg2://postgres:postgres@localhost:5432/postgres'\n",
        )
        self.assert_finding(self.findings(), "database.default_credentials", "FAIL", "default_postgres_pair")

        self.write_good_repo()
        compose = good_compose().replace('xpack.security.enabled: "true"', 'xpack.security.enabled: "false"')
        self.write_text(COMPOSE_REL_PATH, compose)
        self.assert_finding(self.findings(), "compose.elasticsearch_security", "FAIL", "=false")

    def test_direct_cli_reviews_production_compose_and_emits_json(self) -> None:
        self.write_good_repo()
        output = self.root / "r3.json"
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-root", str(self.root), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual("PASS", payload["status"])
        self.assertEqual("static-production-contract", payload["checker"])
        check_ids = {finding["check_id"] for finding in payload["findings"]}
        self.assertIn("compose.production_policy", check_ids)

    def test_contract_10_phase_b_workflow_families_pass(self) -> None:
        self.write_good_repo()
        findings = self.findings()
        for check_id in (
            "workflow.frontend_component_e2e",
            "workflow.security_scans",
            "artifact_metadata.immutable_release",
            "workflow.image_vulnerability_scan",
            "workflow.required_convergence",
            "branch_protection.required_checks",
        ):
            with self.subTest(check_id=check_id):
                self.assertEqual("PASS", findings[check_id].status, findings[check_id].evidence)

    def test_frontend_component_e2e_rejects_nonexecution_and_bypass(self) -> None:
        mutations = (
            ("pnpm install --frozen-lockfile", "pnpm install", "frontend_frozen_install=missing"),
            ("pnpm test:e2e\n", "pnpm test:e2e --list\n", "blocking_pnpm_test_e2e=missing"),
            (
                "        run: pnpm test:e2e\n",
                "        if: success()\n        run: pnpm test:e2e\n",
                "frontend_component_e2e_job=unavailable",
            ),
        )
        for old, new, evidence in mutations:
            with self.subTest(evidence=evidence):
                self.write_good_repo()
                mutated_job = FRONTEND_COMPONENT_E2E_JOB.replace(old, new, 1)
                workflow = good_workflow().replace(FRONTEND_COMPONENT_E2E_JOB, mutated_job)
                self.write_text(".github/workflows/backend-tests.yml", workflow)
                self.assert_finding(self.findings(), "workflow.frontend_component_e2e", "FAIL", evidence)

    def test_security_requires_blocking_frontend_audit_after_frozen_install(self) -> None:
        for replacement, evidence in (
            ("pnpm audit --prod --audit-level high || true", "pnpm_audit_prod_high=missing"),
            ("pnpm audit --audit-level high", "pnpm_audit_prod_high=missing"),
        ):
            with self.subTest(replacement=replacement):
                self.write_good_repo()
                workflow = good_workflow().replace("pnpm audit --prod --audit-level high", replacement, 1)
                self.write_text(".github/workflows/backend-tests.yml", workflow)
                self.assert_finding(self.findings(), "workflow.security_scans", "FAIL", evidence)

        self.write_good_repo()
        workflow = good_workflow().replace(
            "pnpm install --frozen-lockfile",
            "pnpm install",
            1,
        )
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        self.assert_finding(self.findings(), "workflow.security_scans", "FAIL", "frontend_frozen_install=missing")

    def test_security_requires_fixed_git_classification_and_fail_closed_public_audit(self) -> None:
        mutations = (
            (
                "repository: 123rrr4tttt/functorial-kit",
                "repository: example/other-kit",
                "functorial_kit_source_checkout=missing_or_nonunique",
            ),
            (
                "check_functorial_kit_dependency_audit.py",
                "omitted_functorial_kit_dependency_audit.py",
                "functorial_kit_dependency_audit=missing",
            ),
            (
                'pip-audit -r "${RUNNER_TEMP}/mrw-public-pypi-requirements.txt" --strict',
                'pip-audit -r "${RUNNER_TEMP}/mrw-public-pypi-requirements.txt"',
                "pip_audit_public_strict=missing",
            ),
            (
                'pip-audit -r "${RUNNER_TEMP}/mrw-public-pypi-requirements.txt" --strict',
                "pip-audit -r main/backend/requirements.txt --strict",
                "pip_audit_public_strict=missing",
            ),
            (
                "--manifest tools/functorial-kit/consumer-gate.manifest.json",
                "--manifest tools/functorial-kit/other.json",
                "functorial_kit_dependency_audit=missing",
            ),
            (
                "--source-checkout .ci/functorial-kit-source",
                "--source-checkout .ci/other-source",
                "functorial_kit_dependency_audit=missing",
            ),
        )
        for old, new, evidence in mutations:
            with self.subTest(evidence=evidence):
                self.write_good_repo()
                workflow = good_workflow().replace(old, new, 1)
                self.write_text(".github/workflows/backend-tests.yml", workflow)
                self.assert_finding(self.findings(), "workflow.security_scans", "FAIL", evidence)

        self.write_good_repo()
        bandit_step = "      - run: bandit -q -r main/backend/app\n"
        public_audit_step = (
            '      - run: pip-audit -r "${RUNNER_TEMP}/mrw-public-pypi-requirements.txt" --strict\n'
        )
        prefix, after_bandit = SECURITY_JOB.split(bandit_step, 1)
        classifier_step, suffix = after_bandit.split(public_audit_step, 1)
        reordered = prefix + bandit_step + public_audit_step + classifier_step + suffix
        workflow = good_workflow().replace(SECURITY_JOB, reordered, 1)
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        self.assert_finding(
            self.findings(),
            "workflow.security_scans",
            "FAIL",
            "pip_audit_public_strict=not_after_functorial_kit_classification",
        )

    def test_artifact_metadata_rejects_single_generic_image_regression(self) -> None:
        self.write_good_repo()
        mutated_job = ARTIFACT_JOB.replace("id: build-frontend", "id: omitted-frontend", 1).replace(
            "id: build-migration-runner", "id: omitted-migration-runner", 1
        )
        workflow = good_workflow().replace(ARTIFACT_JOB, mutated_job)
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        self.assert_finding(self.findings(), "artifact_metadata.immutable_release", "FAIL", "artifact_build_count=1")

    def test_artifact_metadata_rejects_identity_predicate_builder_and_authority_regressions(self) -> None:
        self.write_good_repo()
        workflow = good_workflow().replace(
            "mrw-local/canonical-frontend:${{ github.sha }}",
            "mrw-local/canonical-backend:${{ github.sha }}",
            1,
        )
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        self.assert_finding(
            self.findings(),
            "artifact_metadata.immutable_release",
            "FAIL",
            "artifact_build_role=ambiguous_or_duplicate",
        )

        self.write_good_repo()
        mutated_job = ARTIFACT_JOB.replace("          provenance: true", "          provenance: false", 1)
        mutated_job = mutated_job.replace("          context: main/frontend-modern", "          context: .", 1)
        workflow = good_workflow().replace(ARTIFACT_JOB, mutated_job)
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        findings = self.findings()
        self.assert_finding(
            findings,
            "artifact_metadata.immutable_release",
            "FAIL",
            "artifact_backend.provenance_and_sbom=missing",
        )
        self.assert_finding(
            findings,
            "artifact_metadata.immutable_release",
            "FAIL",
            "artifact_frontend.context=invalid",
        )

        for old, new, evidence in (
            ("https://slsa.dev/provenance/", "https://invalid.example/predicate", "attestation_content_validation=missing"),
            ("id: rebuild-builder", "id: rebuild-builder-alias", "independent_builders=missing"),
            ("status = \"UNEXECUTED_AUTHORITY_REQUIRED\"", "status = \"UNEXECUTED\"", "authority_boundary=missing"),
            ("ceiling = \"PRODUCTION_RELEASE_NOT_AUTHORIZED\"", "ceiling = \"UNKNOWN\"", "authority_boundary=missing"),
        ):
            with self.subTest(evidence=evidence):
                self.write_good_repo()
                mutated_job = ARTIFACT_JOB.replace(old, new, 1)
                workflow = good_workflow().replace(ARTIFACT_JOB, mutated_job)
                self.write_text(".github/workflows/backend-tests.yml", workflow)
                self.assert_finding(self.findings(), "artifact_metadata.immutable_release", "FAIL", evidence)

        self.write_good_repo()
        mutated_job = ARTIFACT_JOB.replace(
            "ceiling = \"PRODUCTION_RELEASE_NOT_AUTHORIZED\"",
            "ceiling = \"PRODUCTION_RELEASE_NOT_AUTHORIZED\"\n          cosign sign --yes registry.invalid/image@sha256:deadbeef",
            1,
        )
        workflow = good_workflow().replace(ARTIFACT_JOB, mutated_job)
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        self.assert_finding(self.findings(), "artifact_metadata.immutable_release", "FAIL", "authority_write_present_in_preflight")

    def test_image_scan_rejects_rebuild_nonblocking_wrong_bundle_and_missing_validation(self) -> None:
        mutations = (
            (
                "needs: artifact-metadata-check",
                "needs: security-check",
                "canonical_artifact_dependency=missing",
            ),
            (
                "immutable-release-metadata/frontend/image.oci.tar",
                "rebuild-output/frontend.oci.tar",
                "canonical_oci_scan_missing=frontend",
            ),
            (
                "--exit-code 1 --severity HIGH,CRITICAL",
                "--exit-code 0 --severity HIGH,CRITICAL",
                "canonical_oci_scan_missing=backend",
            ),
            (
                "run: docker run --rm aquasec/trivy:0.67.2 image --input immutable-release-metadata/migration-runner/image.oci.tar",
                "run: echo docker run --rm aquasec/trivy:0.67.2 image --input immutable-release-metadata/migration-runner/image.oci.tar",
                "canonical_oci_scan_missing=migration-runner",
            ),
            (
                "      - name: Scan backend canonical OCI\n",
                "      - name: Scan backend canonical OCI\n        continue-on-error: true\n",
                "image_vulnerability_scan_job=unavailable",
            ),
            ("SchemaVersion", "SchemaMarker", "persisted_scan_content_validation=missing"),
        )
        for old, new, evidence in mutations:
            with self.subTest(evidence=evidence):
                self.write_good_repo()
                mutated_job = IMAGE_SCAN_JOB.replace(old, new, 1)
                workflow = good_workflow().replace(IMAGE_SCAN_JOB, mutated_job)
                self.write_text(".github/workflows/backend-tests.yml", workflow)
                self.assert_finding(self.findings(), "workflow.image_vulnerability_scan", "FAIL", evidence)

        self.write_good_repo()
        injected = IMAGE_SCAN_JOB.replace(
            "      - uses: actions/upload-artifact@v4",
            "      - id: forbidden-build\n        uses: docker/build-push-action@v6\n      - uses: actions/upload-artifact@v4",
            1,
        )
        workflow = good_workflow().replace(IMAGE_SCAN_JOB, injected)
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        self.assert_finding(self.findings(), "workflow.image_vulnerability_scan", "FAIL", "canonical_scan_rebuild=forbidden")

    def test_branch_and_convergence_require_both_new_jobs(self) -> None:
        self.write_good_repo()
        branch_path = self.root / ".github/branch-protection-required-checks.json"
        branch = json.loads(branch_path.read_text(encoding="utf-8"))
        branch["required_checks"].remove("frontend-component-e2e-check")
        self.write_text(".github/branch-protection-required-checks.json", json.dumps(branch))
        self.assert_finding(
            self.findings(),
            "branch_protection.required_checks",
            "FAIL",
            "required_check_not_required:frontend-component-e2e",
        )

        self.write_good_repo()
        workflow = good_workflow().replace(
            "      - image-vulnerability-scan-check\n",
            "",
            1,
        )
        self.write_text(".github/workflows/backend-tests.yml", workflow)
        self.assert_finding(
            self.findings(),
            "workflow.required_convergence",
            "FAIL",
            "required_convergence_needs_missing=image-vulnerability-scan-check",
        )

    def test_explicit_cleanup_diagnostics_and_upload_may_use_failure_or_always(self) -> None:
        contract = checker.CheckContract("docker-config-check", ".github/workflows/backend-tests.yml")
        upload_workflow = required_workflow(
            "${{ failure() }}",
            step_name="Upload docker compose diagnostics",
            uses="actions/upload-artifact@v4",
        )
        positive_cases = (
            required_workflow("${{ failure() }}", step_name="Collect docker compose diagnostics"),
            upload_workflow,
            required_workflow("always()", step_name="Teardown"),
            required_workflow("${{ always() }}", step_name="Cleanup"),
        )
        for workflow in positive_cases:
            with self.subTest(step=workflow["jobs"]["docker-config-check"]["steps"][0]["name"]):
                job = checker.job_for_required_check(workflow, contract)
                self.assertEqual("docker-config-check", job["name"])

    def test_core_steps_and_nonconforming_support_steps_remain_fail_closed(self) -> None:
        contract = checker.CheckContract("docker-config-check", ".github/workflows/backend-tests.yml")
        negative_cases = (
            required_workflow("failure()", step_name="Run contract"),
            required_workflow("always()", step_name="Run contract"),
            required_workflow("success()", step_name="Teardown"),
        )
        for workflow in negative_cases:
            with self.subTest(step=workflow["jobs"]["docker-config-check"]["steps"][0]["name"]):
                with self.assertRaisesRegex(
                    checker.StrictParseError,
                    "required_step_condition_unsupported:docker-config-check",
                ):
                    checker.job_for_required_check(workflow, contract)

        with self.assertRaisesRegex(
            checker.StrictParseError,
            "required_step_continue_on_error:docker-config-check",
        ):
            checker.job_for_required_check(
                required_workflow(
                    "failure()",
                    step_name="Upload",
                    uses="actions/upload-artifact@v4",
                    continue_on_error=True,
                ),
                contract,
            )


if __name__ == "__main__":
    unittest.main()
