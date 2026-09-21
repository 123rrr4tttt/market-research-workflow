from __future__ import annotations

import importlib
import subprocess
import unittest
from unittest.mock import patch

from scripts._current_dev_git import changed_files_in_worktree, run_git


class CurrentDevGitHelpersTest(unittest.TestCase):
    def test_all_current_dev_plan_scripts_share_one_implementation(self) -> None:
        for wave in range(8, 21):
            with self.subTest(wave=wave):
                module = importlib.import_module(f"scripts.check_current_dev_wave{wave}_plan")

                self.assertIs(module.run_git, run_git)
                self.assertIs(module.changed_files_in_worktree, changed_files_in_worktree)

    def test_run_git_invokes_git_and_strips_stdout(self) -> None:
        completed = subprocess.CompletedProcess(
            ["git", "status"], returncode=0, stdout="  value  \n", stderr="noise\n"
        )

        with patch("scripts._current_dev_git.subprocess.run", return_value=completed) as run:
            self.assertEqual(run_git(["status"]), "value")

        run.assert_called_once_with(
            ["git", "status"], text=True, capture_output=True, check=False
        )

    def test_run_git_reports_stderr_without_raising_subprocess_error(self) -> None:
        completed = subprocess.CompletedProcess(
            ["git", "merge-base"], returncode=128, stdout="stdout detail\n", stderr="stderr detail\n"
        )

        with patch("scripts._current_dev_git.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, r"^git merge-base failed: stderr detail$"):
                run_git(["merge-base"])

    def test_changed_files_in_worktree_preserves_order_and_renames(self) -> None:
        output = "\n M first.py\nR  old.py -> new.py\n\n?? last.py\n"

        with patch("scripts._current_dev_git.run_git", return_value=output) as run:
            self.assertEqual(
                changed_files_in_worktree(),
                ["first.py", "new.py", "last.py"],
            )

        run.assert_called_once_with(["status", "--porcelain"])


if __name__ == "__main__":
    unittest.main()
