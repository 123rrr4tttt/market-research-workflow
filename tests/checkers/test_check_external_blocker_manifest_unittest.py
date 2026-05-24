#!/usr/bin/env python3
"""Focused tests for the external-blocker manifest checker."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "checkers"
    / "check_external_blocker_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("check_external_blocker_manifest", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


DEV_PLANS_ROOT = Path("development/latest-dev-docs/development-plans")
CURRENT_DEV = DEV_PLANS_ROOT / "CURRENT_DEV"
CURRENT_DEV_INDEX = CURRENT_DEV / "INDEX.md"
EXTERNAL_ROOT = DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED"
MANIFEST = DEV_PLANS_ROOT / "EXTERNAL_BLOCKER_MANIFEST.v1.json"


class ExternalBlockerManifestTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        dev_plans = root / DEV_PLANS_ROOT
        current_dev = root / CURRENT_DEV
        external_root = root / EXTERNAL_ROOT
        closed_root = root / "docs/development/development-plans/ARCHIVE_CLOSED"
        retired_root = root / DEV_PLANS_ROOT / "ARCHIVE_RETIRED"
        for directory in (current_dev / "main", external_root, closed_root, retired_root):
            directory.mkdir(parents=True, exist_ok=True)
        (root / "scripts").mkdir()
        (root / "scripts/check_example_external_provider.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        (root / "scripts/check_extra.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

        (dev_plans / "INDEX.md").write_text(
            "# Development Plans Index\n\n- [CURRENT_DEV/INDEX.md](./CURRENT_DEV/INDEX.md)\n",
            encoding="utf-8",
        )
        (current_dev / "INDEX.md").write_text(
            "\n".join(
                [
                    "# CURRENT_DEV Index",
                    "",
                    "## 剩余状态分布",
                    "",
                    "- `partial`: 0",
                    "- `not_closed`: 0",
                    "- `no_closure_claim`: 0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (external_root / "INDEX.md").write_text(
            "# External Blocked\n\n- [External Topic](./external-topic/INDEX.md)\n",
            encoding="utf-8",
        )
        (closed_root / "INDEX.md").write_text("# Closed\n", encoding="utf-8")
        (retired_root / "INDEX.md").write_text("# Retired\n", encoding="utf-8")

        topic = external_root / "external-topic"
        topic.mkdir()
        (topic / "INDEX.md").write_text(
            "\n".join(
                [
                    "# External Topic",
                    "",
                    "Status: external_blocked",
                    "Code: main/backend/app/services/example.py",
                    "Gate: check_external_provider gate readback",
                    "External blocker: live provider not_verified",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        allowlist = {
            "schema": "development-plans-target-topic-allowlist/v1",
            "external_blocker_manifest": MANIFEST.as_posix(),
            "target_roots": [
                {
                    "path": CURRENT_DEV.as_posix(),
                    "status": "active_current",
                    "entrypoint": CURRENT_DEV_INDEX.as_posix(),
                    "allowed_non_topic_dirs": ["main"],
                },
                {
                    "path": "docs/development/development-plans/ARCHIVE_CLOSED",
                    "status": "closed",
                    "entrypoint": "docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md",
                },
                {
                    "path": EXTERNAL_ROOT.as_posix(),
                    "status": "external_blocked",
                    "entrypoint": (EXTERNAL_ROOT / "INDEX.md").as_posix(),
                },
                {
                    "path": (DEV_PLANS_ROOT / "ARCHIVE_RETIRED").as_posix(),
                    "status": "retired",
                    "entrypoint": (DEV_PLANS_ROOT / "ARCHIVE_RETIRED/INDEX.md").as_posix(),
                },
            ],
        }
        (dev_plans / "TARGET_TOPIC_ALLOWLIST.json").write_text(
            json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.write_valid_manifest(root)
        return root

    def write_valid_manifest(self, root: Path, *, targets: list[dict[str, object]] | None = None) -> None:
        if targets is None:
            targets = [
                {
                    "path": (EXTERNAL_ROOT / "external-topic").as_posix(),
                    "dependency_type": "provider",
                    "blocked_on": "Live provider replay is not available in repo-local deterministic gates.",
                    "external_surfaces": ["live provider"],
                    "repo_local_evidence": [(EXTERNAL_ROOT / "external-topic/INDEX.md").as_posix()],
                    "evidence_required": ["probe", "run_output", "manual_check"],
                    "probe_or_manual_evidence": {
                        "mode": "probe",
                        "command": "python scripts/check_example_external_provider.py --live-evidence-json evidence.json",
                        "last_run_at": "pending_external",
                        "result_artifact": "development/latest-dev-docs/automation-runs/external-provider-live/README.md",
                        "exit_code_expectation": "0",
                        "result_summary": "Must attach live provider output before unblocking.",
                    },
                    "exit_criteria": [
                        {
                            "id": "live-provider-replay",
                            "state": "blocked",
                            "evidence": "development/latest-dev-docs/automation-runs/external-provider-live/README.md",
                            "note": "Provider replay has not been attached.",
                        }
                    ],
                    "owner_surface": {
                        "owner": "external-blocker-review",
                        "surface": (EXTERNAL_ROOT / "INDEX.md").as_posix(),
                    },
                }
            ]
        payload = {
            "schema": "external-blocker-manifest/v1",
            "updated": "2026-05-23",
            "targets": targets,
        }
        (root / MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_valid_manifest_covers_external_targets(self) -> None:
        result = checker.check(self.make_repo())

        self.assertTrue(result.ok, result.problems)
        self.assertEqual(1, len(result.external_targets))
        self.assertEqual(result.external_targets, result.manifest_targets)

    def test_rejects_missing_manifest_entry(self) -> None:
        root = self.make_repo()
        self.write_valid_manifest(root, targets=[])

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("targets must be a non-empty list" in problem.message for problem in result.problems))

    def test_rejects_extra_manifest_target(self) -> None:
        root = self.make_repo()
        extra = {
            "path": "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/not-a-target",
            "dependency_type": "provider",
            "blocked_on": "Extra topic.",
            "repo_local_evidence": [(EXTERNAL_ROOT / "external-topic/INDEX.md").as_posix()],
            "evidence_required": ["probe"],
            "probe_or_manual_evidence": {
                "mode": "probe",
                "command": "python scripts/check_extra.py",
                "last_run_at": "pending_external",
                "result_artifact": "development/latest-dev-docs/automation-runs/extra/README.md",
                "exit_code_expectation": "0",
                "result_summary": "extra",
            },
            "exit_criteria": [
                {
                    "id": "extra",
                    "state": "blocked",
                    "evidence": "development/latest-dev-docs/automation-runs/extra/README.md",
                    "note": "extra",
                }
            ],
            "owner_surface": {"owner": "external-blocker-review", "surface": (EXTERNAL_ROOT / "INDEX.md").as_posix()},
        }
        valid = json.loads((root / MANIFEST).read_text(encoding="utf-8"))["targets"][0]
        self.write_valid_manifest(root, targets=[valid, extra])

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("not an external_blocked review target" in problem.message for problem in result.problems))

    def test_rejects_missing_repo_local_evidence_file(self) -> None:
        root = self.make_repo()
        payload = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        payload["targets"][0]["repo_local_evidence"] = ["missing.md"]
        (root / MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("repo_local_evidence file is missing" in problem.message for problem in result.problems))

    def test_rejects_missing_evidence_required(self) -> None:
        root = self.make_repo()
        payload = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        payload["targets"][0].pop("evidence_required")
        (root / MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("evidence_required must be a non-empty string list" in problem.message for problem in result.problems))

    def test_rejects_invalid_evidence_required_value(self) -> None:
        root = self.make_repo()
        payload = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        payload["targets"][0]["evidence_required"] = ["probe", "unsupported"]
        (root / MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("evidence_required has invalid values" in problem.message for problem in result.problems))


if __name__ == "__main__":
    unittest.main()
