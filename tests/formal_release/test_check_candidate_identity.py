from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "formal_release" / "check_candidate_identity.py"
SPEC = importlib.util.spec_from_file_location("check_candidate_identity", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def configured_python_matrix() -> tuple[Path, ...]:
    """Use an explicit execution-environment matrix without fabricating venvs."""
    raw = os.environ.get("MRW_TEST_PYTHON_EXECUTABLES")
    if raw is None:
        return (Path(".venv/bin/python"), Path("main/backend/.venv311/bin/python"))
    values = json.loads(raw)
    if (
        not isinstance(values, list) or not values
        or any(not isinstance(value, str) or not Path(value).is_absolute() for value in values)
        or len(values) != len(set(values))
    ):
        raise ValueError("MRW_TEST_PYTHON_EXECUTABLES requires unique absolute interpreter paths")
    return tuple(Path(value) for value in values)


class CandidateIdentityPreflightTestCase(unittest.TestCase):
    SCRIPT = SCRIPT_PATH
    PYTHONS = configured_python_matrix()

    def test_explicit_runtime_matrix_is_nonempty_unique_and_absolute(self) -> None:
        with mock.patch.dict(os.environ, {"MRW_TEST_PYTHON_EXECUTABLES": json.dumps([sys.executable])}):
            self.assertEqual((Path(sys.executable),), configured_python_matrix())
        for value in ([], ["relative/python"], [sys.executable, sys.executable], {}, [1]):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"MRW_TEST_PYTHON_EXECUTABLES": json.dumps(value)}):
                    with self.assertRaises(ValueError):
                        configured_python_matrix()

    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name).resolve()

    def git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(
            ("git", "-C", str(root), *args),
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def init_repo(self) -> tuple[Path, str, str]:
        root = self.make_repo()
        self.git(root, "init")
        self.git(root, "config", "user.email", "ci@example.com")
        self.git(root, "config", "user.name", "CI")
        (root / "tracked.txt").write_text("initial\n", encoding="utf-8")
        self.git(root, "add", "tracked.txt")
        self.git(root, "commit", "-m", "initial")
        commit = self.git(root, "rev-parse", "HEAD")
        tree = self.git(root, "rev-parse", "HEAD^{tree}")
        return root, commit, tree

    def findings(self, report: object) -> dict[str, dict[str, object]]:
        payload = report.to_dict()  # type: ignore[no-any-return]
        return {item["check_id"]: item for item in payload["findings"]}

    def run_main(self, argv: list[str]) -> tuple[int, str]:
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            exit_code = checker.main(argv)
        return exit_code, buffer.getvalue()

    def run_cli(self, python: Path, *argv: str) -> subprocess.CompletedProcess[str]:
        self.assertTrue(python.exists(), f"python executable missing: {python}")
        return subprocess.run(
            (str(python), str(self.SCRIPT), *argv),
            check=False,
            capture_output=True,
            text=True,
        )

    def base_argv(self, root: Path, commit: str, tree: str, *extra: str) -> list[str]:
        return [
            "--repo-root",
            str(root),
            "--expected-commit",
            commit,
            "--expected-tree",
            tree,
            "--candidate-strategy",
            "REMEDIATION_INCLUSIVE_RELEASE",
            *extra,
        ]

    def test_exact_clean_match_passes_and_writes_json(self) -> None:
        root, commit, tree = self.init_repo()
        output = self.make_repo() / "candidate.json"

        exit_code, stdout = self.run_main(self.base_argv(root, commit, tree, "--output", str(output)))
        payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(0, exit_code)
        self.assertEqual(payload, json.loads(stdout))
        self.assertEqual(checker.CHECKER, payload["checker"])
        self.assertIs(payload["authoritative"], False)
        self.assertEqual("preflight", payload["derived_as"])
        self.assertEqual("PASS", payload["status"])
        self.assertEqual(
            [
                "candidate.strategy",
                "candidate.commit",
                "candidate.tree",
                "candidate.dirty_tracked",
                "candidate.untracked",
            ],
            [item["check_id"] for item in payload["findings"]],
        )
        self.assertTrue(all(item["status"] == "PASS" for item in payload["findings"]))

    def test_commit_mismatch_fails(self) -> None:
        root, commit, tree = self.init_repo()
        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit="0" * 40,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )
        findings = self.findings(report)

        self.assertEqual("FAIL", report.status)
        self.assertEqual("FAIL", findings["candidate.commit"]["status"])
        self.assertEqual("PASS", findings["candidate.tree"]["status"])
        self.assertEqual("PASS", findings["candidate.dirty_tracked"]["status"])
        self.assertEqual("PASS", findings["candidate.untracked"]["status"])
        self.assertEqual(f"observed={commit}", findings["candidate.commit"]["evidence"][1])

    def test_external_output_is_create_only(self) -> None:
        root, commit, tree = self.init_repo()
        output = self.make_repo() / "candidate.json"
        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )

        checker.write_report(output, report, root)
        self.assertEqual(report.to_json(), output.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(
            checker.CandidateIdentityOutputError,
            "create-only target already exists",
        ):
            checker.write_report(output, report, root)
        self.assertEqual(report.to_json(), output.read_text(encoding="utf-8"))

    def test_existing_regular_output_is_not_overwritten(self) -> None:
        root, commit, tree = self.init_repo()
        output = self.make_repo() / "candidate.json"
        output.write_text("sentinel\n", encoding="utf-8")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code, stdout = self.run_main(
                self.base_argv(root, commit, tree, "--output", str(output))
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("create-only target already exists", stderr.getvalue())
        self.assertEqual("sentinel\n", output.read_text(encoding="utf-8"))

    def test_symlink_output_is_not_followed_or_overwritten(self) -> None:
        root, commit, tree = self.init_repo()
        output_dir = self.make_repo()
        target = output_dir / "sentinel.json"
        target.write_text("sentinel\n", encoding="utf-8")
        output = output_dir / "candidate.json"
        os.symlink(target, output)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code, stdout = self.run_main(
                self.base_argv(root, commit, tree, "--output", str(output))
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("create-only target already exists", stderr.getvalue())
        self.assertEqual("sentinel\n", target.read_text(encoding="utf-8"))
        self.assertTrue(output.is_symlink())

    def test_symlink_ancestor_output_is_rejected(self) -> None:
        root, commit, tree = self.init_repo()
        external_dir = self.make_repo()
        link_root = self.make_repo() / "external-link"
        os.symlink(external_dir, link_root)
        output = link_root / "candidate.json"

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code, stdout = self.run_main(
                self.base_argv(root, commit, tree, "--output", str(output))
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("output ancestor must not be a symbolic link", stderr.getvalue())
        self.assertFalse((external_dir / "candidate.json").exists())

    def test_output_inside_candidate_is_rejected_without_pollution(self) -> None:
        root, commit, tree = self.init_repo()
        output = root / "candidate.json"

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code, stdout = self.run_main(
                self.base_argv(root, commit, tree, "--output", str(output))
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("output must be outside candidate repository", stderr.getvalue())
        self.assertFalse(output.exists())
        self.assertEqual("", self.git(root, "status", "--porcelain=v1"))

    def test_repo_subdirectory_cannot_write_output_in_repository_root(self) -> None:
        root, commit, tree = self.init_repo()
        subdirectory = root / "nested"
        subdirectory.mkdir()
        output = root / "candidate.json"

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code, stdout = self.run_main(
                self.base_argv(subdirectory, commit, tree, "--output", str(output))
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("output must be outside candidate repository", stderr.getvalue())
        self.assertFalse(output.exists())
        self.assertEqual("", self.git(root, "status", "--porcelain=v1"))

    def test_git_environment_cannot_redirect_identity_or_output_confinement(self) -> None:
        root, commit, tree = self.init_repo()
        other, _other_commit, _other_tree = self.init_repo()
        output = root / "candidate.json"
        poisoned = {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)}

        stderr = io.StringIO()
        with mock.patch.dict(os.environ, poisoned), contextlib.redirect_stderr(stderr):
            report = checker.evaluate_candidate_identity(
                repo_root=root,
                expected_commit=commit,
                expected_tree=tree,
                candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
            )
            exit_code, stdout = self.run_main(
                self.base_argv(root, commit, tree, "--output", str(output))
            )

        self.assertEqual("PASS", report.status)
        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout)
        self.assertIn("output must be outside candidate repository", stderr.getvalue())
        self.assertFalse(output.exists())
        self.assertEqual("", self.git(root, "status", "--porcelain=v1"))

    def test_git_environment_clears_config_rewrites_for_remote(self) -> None:
        root, _commit, _tree = self.init_repo()
        original_remote = "https://example.test/source.git"
        self.git(root, "remote", "add", "origin", original_remote)
        malicious_config = self.make_repo() / "global-git-config"
        malicious_config.write_text(
            '[url "https://evil.test/"]\n'
            "\tinsteadOf = https://example.test/\n",
            encoding="utf-8",
        )
        poisoned = {
            "GIT_CONFIG_GLOBAL": str(malicious_config),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.https://example.test/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://evil.test/",
        }

        with mock.patch.dict(os.environ, poisoned):
            output, error = checker._git_output(root, "remote", "get-url", "origin")

        self.assertIsNone(error)
        self.assertEqual(original_remote, output.strip())

    def test_home_and_xdg_gitconfigs_cannot_affect_git_reads(self) -> None:
        root, commit, tree = self.init_repo()
        original_remote = "https://example.test/source.git"
        self.git(root, "remote", "add", "origin", original_remote)
        (root / ".git/info/attributes").write_text(
            "tracked.txt filter=poison\n",
            encoding="utf-8",
        )

        home = self.make_repo()
        xdg = self.make_repo()
        hook_directory = self.make_repo()
        (home / ".gitconfig").write_text(
            '[url "https://home-evil.test/"]\n'
            "\tinsteadOf = https://example.test/\n"
            "[core]\n"
            f"\thooksPath = {hook_directory}\n",
            encoding="utf-8",
        )
        (xdg / "git").mkdir()
        (xdg / "git/config").write_text(
            '[filter "poison"]\n'
            "\tclean = false\n"
            "\trequired = true\n",
            encoding="utf-8",
        )

        with mock.patch.dict(
            os.environ,
            {"HOME": str(home), "XDG_CONFIG_HOME": str(xdg)},
        ):
            remote, remote_error = checker._git_output(root, "remote", "get-url", "origin")
            report = checker.evaluate_candidate_identity(
                repo_root=root,
                expected_commit=commit,
                expected_tree=tree,
                candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
            )
            tree_output, tree_error = checker._git_output(root, "ls-tree", "-r", "-z", "HEAD")
            isolated_env = checker._git_env()

        self.assertIsNone(remote_error)
        self.assertEqual(original_remote, remote.strip())
        self.assertEqual("PASS", report.status)
        self.assertIsNone(tree_error)
        self.assertIn("tracked.txt", tree_output)
        self.assertEqual("1", isolated_env["GIT_CONFIG_NOSYSTEM"])
        self.assertEqual(os.devnull, isolated_env["GIT_CONFIG_GLOBAL"])

    def test_local_fsmonitor_is_disabled_for_git_reads(self) -> None:
        root, commit, tree = self.init_repo()
        marker = self.make_repo() / "fsmonitor-ran"
        hook = self.make_repo() / "fsmonitor-hook"
        hook.write_text(
            f"#!/bin/sh\ntouch '{marker}'\nexit 1\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        self.git(root, "config", "core.fsmonitor", str(hook))

        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )

        self.assertEqual("PASS", report.status)
        self.assertFalse(marker.exists())

    def test_replace_refs_cannot_substitute_candidate_objects(self) -> None:
        root, commit, tree = self.init_repo()
        original_listing = self.git(root, "ls-tree", "-r", "-z", commit)
        (root / "tracked.txt").write_text("replacement\n", encoding="utf-8")
        self.git(root, "add", "tracked.txt")
        self.git(root, "commit", "-m", "replacement")
        replacement_commit = self.git(root, "rev-parse", "HEAD")
        self.git(root, "checkout", "--detach", commit)
        self.git(root, "replace", commit, replacement_commit)

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIT_NO_REPLACE_OBJECTS", None)
            self.assertNotEqual(tree, self.git(root, "rev-parse", "HEAD^{tree}"))
            self.assertNotEqual("", self.git(root, "status", "--porcelain=v1"))
            report = checker.evaluate_candidate_identity(
                repo_root=root,
                expected_commit=commit,
                expected_tree=tree,
                candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
            )
            observed_tree, tree_error = checker._git_output(root, "rev-parse", "HEAD^{tree}")
            tree_listing, listing_error = checker._git_output(root, "ls-tree", "-r", "-z", "HEAD")
            isolated_env = checker._git_env()

        self.assertEqual("PASS", report.status)
        self.assertIsNone(tree_error)
        self.assertEqual(tree, observed_tree.strip())
        self.assertIsNone(listing_error)
        self.assertEqual(original_listing, tree_listing.strip())
        self.assertEqual("1", isolated_env["GIT_NO_REPLACE_OBJECTS"])

    def test_output_parent_swap_cannot_redirect_write_into_candidate(self) -> None:
        root, commit, tree = self.init_repo()
        container = self.make_repo()
        output_parent = container / "receipt"
        output_parent.mkdir()
        moved_parent = container / "receipt-original"
        output = output_parent / "candidate.json"
        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )
        original_write = checker.write_create_only_bytes

        def redirect_before_write(path: Path, payload: bytes, identities: object) -> Path:
            output_parent.rename(moved_parent)
            output_parent.symlink_to(root, target_is_directory=True)
            return original_write(path, payload, identities)

        with mock.patch.object(checker, "write_create_only_bytes", side_effect=redirect_before_write):
            with self.assertRaisesRegex(checker.CandidateIdentityOutputError, "unsafe"):
                checker.write_report(output, report, root)

        self.assertFalse((root / output.name).exists())
        self.assertFalse((moved_parent / output.name).exists())

    def test_candidate_root_rename_to_output_parent_is_rejected(self) -> None:
        root, commit, tree = self.init_repo()
        container = self.make_repo()
        output_parent = container / "receipt"
        output_parent.mkdir()
        output = output_parent / "candidate.json"
        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )
        original_write = checker.write_create_only_bytes

        def rename_candidate_before_write(
            path: Path,
            payload: bytes,
            identities: object,
        ) -> Path:
            root.rename(output_parent)
            return original_write(path, payload, identities)

        with mock.patch.object(
            checker,
            "write_create_only_bytes",
            side_effect=rename_candidate_before_write,
        ):
            with self.assertRaisesRegex(
                checker.CandidateIdentityOutputError,
                "ancestor entered a forbidden checkout",
            ):
                checker.write_report(output, report, root)

        self.assertFalse(output.exists())

    def test_tree_mismatch_fails(self) -> None:
        root, commit, tree = self.init_repo()
        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree="f" * 64,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )
        findings = self.findings(report)

        self.assertEqual("FAIL", report.status)
        self.assertEqual("PASS", findings["candidate.commit"]["status"])
        self.assertEqual("FAIL", findings["candidate.tree"]["status"])
        self.assertEqual("PASS", findings["candidate.dirty_tracked"]["status"])
        self.assertEqual("PASS", findings["candidate.untracked"]["status"])
        self.assertEqual(f"observed={tree}", findings["candidate.tree"]["evidence"][1])

    def test_dirty_tracked_file_fails(self) -> None:
        root, commit, tree = self.init_repo()
        (root / "tracked.txt").write_text("changed\n", encoding="utf-8")

        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )
        findings = self.findings(report)

        self.assertEqual("FAIL", report.status)
        self.assertEqual("PASS", findings["candidate.commit"]["status"])
        self.assertEqual("PASS", findings["candidate.tree"]["status"])
        self.assertEqual("FAIL", findings["candidate.dirty_tracked"]["status"])
        self.assertEqual("PASS", findings["candidate.untracked"]["status"])
        self.assertTrue(
            any(
                str(item).startswith("porcelain=")
                for item in findings["candidate.dirty_tracked"]["evidence"]
            )
        )

    def test_hidden_index_flags_fail_when_porcelain_is_clean(self) -> None:
        cases = (
            ("--assume-unchanged", "h", "assume-unchanged"),
            ("--skip-worktree", "S", "skip-worktree"),
        )
        for option, tag, flag_name in cases:
            with self.subTest(option=option):
                root, commit, tree = self.init_repo()
                self.git(root, "update-index", option, "tracked.txt")
                (root / "tracked.txt").write_text("hidden change\n", encoding="utf-8")
                porcelain = self.git(root, "status", "--porcelain=v1", "--untracked-files=all")
                self.assertEqual("", porcelain)

                report = checker.evaluate_candidate_identity(
                    repo_root=root,
                    expected_commit=commit,
                    expected_tree=tree,
                    candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
                )
                findings = self.findings(report)

                self.assertEqual("FAIL", report.status)
                self.assertEqual("PASS", findings["candidate.commit"]["status"])
                self.assertEqual("PASS", findings["candidate.tree"]["status"])
                self.assertEqual("FAIL", findings["candidate.dirty_tracked"]["status"])
                self.assertEqual("PASS", findings["candidate.untracked"]["status"])
                self.assertIn("hidden_flag_count=1", findings["candidate.dirty_tracked"]["evidence"])
                self.assertIn(
                    f"hidden_flag={tag} {flag_name} tracked.txt",
                    findings["candidate.dirty_tracked"]["evidence"],
                )

    def test_overlay_hidden_index_flags_fail_when_porcelain_is_clean(self) -> None:
        root, commit, tree = self.init_repo()
        self.git(
            root,
            "update-index",
            "--assume-unchanged",
            "tracked.txt",
        )
        self.git(root, "update-index", "--skip-worktree", "tracked.txt")
        (root / "tracked.txt").write_text("hidden change\n", encoding="utf-8")

        self.assertEqual("hidden change\n", (root / "tracked.txt").read_text(encoding="utf-8"))
        porcelain = self.git(root, "status", "--porcelain=v1", "--untracked-files=all")
        self.assertEqual("", porcelain)
        self.assertIn("s tracked.txt", self.git(root, "ls-files", "-t", "-v"))

        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )
        findings = self.findings(report)

        self.assertEqual("FAIL", report.status)
        self.assertEqual("PASS", findings["candidate.commit"]["status"])
        self.assertEqual("PASS", findings["candidate.tree"]["status"])
        self.assertEqual("FAIL", findings["candidate.dirty_tracked"]["status"])
        self.assertEqual("PASS", findings["candidate.untracked"]["status"])
        self.assertIn("hidden_flag_count=1", findings["candidate.dirty_tracked"]["evidence"])
        self.assertIn(
            "hidden_flag=s assume-unchanged+skip-worktree tracked.txt",
            findings["candidate.dirty_tracked"]["evidence"],
        )

    def test_untracked_file_fails(self) -> None:
        root, commit, tree = self.init_repo()
        (root / "untracked.txt").write_text("new\n", encoding="utf-8")

        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="REMEDIATION_INCLUSIVE_RELEASE",
        )
        findings = self.findings(report)

        self.assertEqual("FAIL", report.status)
        self.assertEqual("PASS", findings["candidate.commit"]["status"])
        self.assertEqual("PASS", findings["candidate.tree"]["status"])
        self.assertEqual("PASS", findings["candidate.dirty_tracked"]["status"])
        self.assertEqual("FAIL", findings["candidate.untracked"]["status"])
        self.assertTrue(
            any(
                str(item).startswith("porcelain=??")
                for item in findings["candidate.untracked"]["evidence"]
            )
        )

    def test_invalid_strategy_fails(self) -> None:
        root, commit, tree = self.init_repo()
        report = checker.evaluate_candidate_identity(
            repo_root=root,
            expected_commit=commit,
            expected_tree=tree,
            candidate_strategy="NOT_A_STRATEGY",
        )
        findings = self.findings(report)

        self.assertEqual("FAIL", report.status)
        self.assertEqual("FAIL", findings["candidate.strategy"]["status"])
        self.assertEqual("PASS", findings["candidate.commit"]["status"])
        self.assertEqual("PASS", findings["candidate.tree"]["status"])
        self.assertEqual("PASS", findings["candidate.dirty_tracked"]["status"])
        self.assertEqual("PASS", findings["candidate.untracked"]["status"])
        self.assertIn(
            "allowed=REMEDIATION_INCLUSIVE_RELEASE,PRODUCTION_MAIN_STABILIZATION",
            findings["candidate.strategy"]["evidence"],
        )

    def test_cli_help_runs_in_repo_python_envs(self) -> None:
        for python in self.PYTHONS:
            with self.subTest(python=python):
                result = self.run_cli(python, "--help")
                self.assertEqual(0, result.returncode)
                self.assertIn("--expected-commit", result.stdout)
                self.assertEqual("", result.stderr)

    def test_cli_output_is_marked_and_directly_runnable_in_repo_python_envs(self) -> None:
        root, commit, tree = self.init_repo()
        output_dir = self.make_repo()

        for python in self.PYTHONS:
            with self.subTest(python=python):
                output = output_dir / f"candidate-{python.parent.parent.name}.json"
                result = self.run_cli(
                    python,
                    "--repo-root",
                    str(root),
                    "--expected-commit",
                    commit,
                    "--expected-tree",
                    tree,
                    "--candidate-strategy",
                    "REMEDIATION_INCLUSIVE_RELEASE",
                    "--output",
                    str(output),
                )
                self.assertEqual(0, result.returncode)
                payload = json.loads(output.read_text(encoding="utf-8"))
                self.assertIs(payload["authoritative"], False)
                self.assertEqual("preflight", payload["derived_as"])
                self.assertEqual("PASS", payload["status"])
                self.assertIn('"derived_as": "preflight"', result.stdout)
                self.assertIn('"authoritative": false', result.stdout)


if __name__ == "__main__":
    unittest.main()
