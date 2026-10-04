"""Focused tests for render-only production Compose config preflight."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path
from contextlib import contextmanager
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "formal_release" / "check_production_compose_config.py"
SPEC = importlib.util.spec_from_file_location("check_production_compose_config", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


@contextmanager
def render_only_docker_shim():
    """Provide the docker CLI boundary without a daemon or network access."""
    with tempfile.TemporaryDirectory(prefix="compose-config-shim-") as directory:
        shim = Path(directory) / "docker"
        shim.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                import os
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                if args[0] != "compose" or "config" not in args:
                    print("unsupported docker command", file=sys.stderr)
                    raise SystemExit(2)
                compose_path = Path(args[args.index("-f") + 1])
                if not compose_path.is_file():
                    print("compose file is unavailable", file=sys.stderr)
                    raise SystemExit(1)
                if "PRODUCTION_METRICS_TOKEN" not in os.environ:
                    print("required production environment value is missing", file=sys.stderr)
                    raise SystemExit(1)
                print("{}")
                """
            ).lstrip(),
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        with mock.patch.dict(os.environ, {"PATH": f"{shim.parent}:{os.environ['PATH']}"}):
            yield


class ProductionComposeConfigPreflightTestCase(unittest.TestCase):
    def finding(self, report: object) -> dict[str, object]:
        payload = report.to_dict()  # type: ignore[attr-defined]
        self.assertEqual(1, len(payload["findings"]))
        return payload["findings"][0]  # type: ignore[index,no-any-return]

    def test_synthetic_environment_exactly_covers_required_compose_inputs(self) -> None:
        compose_refs = re.findall(
            r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)(:\?|:-)[^}]*\}",
            (ROOT / checker.COMPOSE_PATH).read_text(encoding="utf-8"),
        )
        required_compose_env = {
            name for name, operator in compose_refs if operator == ":?"
        }
        defaulted_compose_env = {
            name for name, operator in compose_refs if operator == ":-"
        }

        self.assertEqual(set(checker.SYNTHETIC_ENV), required_compose_env)
        self.assertTrue(defaulted_compose_env.isdisjoint(checker.SYNTHETIC_ENV))
        self.assertTrue(all(checker.SYNTHETIC_ENV.values()))

    def test_render_only_preflight_passes_with_preflight_envelope(self) -> None:
        with render_only_docker_shim():
            report = checker.evaluate_production_compose_config(repo_root=ROOT)
        payload = report.to_dict()
        finding = self.finding(report)

        self.assertEqual("PASS", report.status)
        self.assertEqual("production-compose-config-render", payload["checker"])
        self.assertIs(False, payload["authoritative"])
        self.assertEqual("preflight", payload["derived_as"])
        self.assertEqual("production.compose_config", finding["check_id"])
        self.assertIn("mode=config_render_only", finding["evidence"])
        self.assertIn("service_start=false", finding["evidence"])
        self.assertIn("temp_env_cleanup=true", finding["evidence"])

    def test_missing_key_is_fail_and_evidence_contains_no_missing_key_name(self) -> None:
        with render_only_docker_shim():
            report = checker.evaluate_production_compose_config(
                repo_root=ROOT,
                missing_keys=("PRODUCTION_METRICS_TOKEN",),
            )
        payload = report.to_dict()
        finding = self.finding(report)
        serialized = json.dumps(payload)

        self.assertEqual("FAIL", report.status)
        self.assertEqual("FAIL", finding["status"])
        self.assertIn("returncode=1", finding["evidence"])
        self.assertTrue(
            any(
                item.startswith("stderr_sha256=")
                for item in finding["evidence"]
                if isinstance(item, str)
            )
        )
        self.assertNotIn("PRODUCTION_METRICS_TOKEN", serialized)

    def test_compose_failure_is_fail_without_leaking_temp_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compose-config-missing-root-") as directory:
            with render_only_docker_shim():
                report = checker.evaluate_production_compose_config(repo_root=Path(directory))

        finding = self.finding(report)

        self.assertEqual("FAIL", report.status)
        self.assertIn("returncode=1", finding["evidence"])
        self.assertNotIn("compose-config-missing-root-", json.dumps(report.to_dict()))

    def test_cli_writes_and_prints_one_preflight_envelope(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compose-config-cli-") as directory:
            output = Path(directory) / "report.json"
            with render_only_docker_shim():
                completed = subprocess.run(
                    (sys.executable, str(SCRIPT_PATH), "--repo-root", str(ROOT), "--output", str(output)),
                    cwd=ROOT,
                    env={
                        **os.environ,
                        "PRODUCTION_METRICS_TOKEN": "host_must_not_override_synthetic_input",
                    },
                    text=True,
                    capture_output=True,
                    check=False,
                )
            stdout_payload = json.loads(completed.stdout)
            output_payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(stdout_payload, output_payload)
        self.assertIs(False, stdout_payload["authoritative"])
        self.assertEqual("preflight", stdout_payload["derived_as"])
        self.assertEqual("PASS", stdout_payload["status"])


if __name__ == "__main__":
    unittest.main()
