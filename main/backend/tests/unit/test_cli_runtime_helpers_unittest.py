from __future__ import annotations

import importlib
import unittest
from pathlib import Path


class CliRuntimeHelpersTest(unittest.TestCase):
    def test_repo_root_is_repository_root(self) -> None:
        module = importlib.import_module("main.backend.scripts._cli_runtime")

        self.assertEqual(module.repo_root(), Path(__file__).resolve().parents[4])


if __name__ == "__main__":
    unittest.main()
