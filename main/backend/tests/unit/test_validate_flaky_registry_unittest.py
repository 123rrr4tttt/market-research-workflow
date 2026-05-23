from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import validate_flaky_registry

pytestmark = pytest.mark.unit


class ValidateFlakyRegistryUnitTestCase(unittest.TestCase):
    def test_main_accepts_registry_entries_with_required_owners(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "flaky-registry.json"
            output = root / "flaky-registry-report.md"
            registry.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "nodeid": "tests.test_alpha::test_flaky",
                                "service_owner": "backend",
                                "data_owner": "qa",
                                "alert_owner": "ops",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                sys,
                "argv",
                ["validate_flaky_registry.py", "--registry", str(registry), "--output", str(output)],
            ):
                self.assertEqual(validate_flaky_registry.main(), 0)

            self.assertIn("- status: `pass`", output.read_text(encoding="utf-8"))

    def test_main_rejects_registry_entries_missing_owners(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "flaky-registry.json"
            output = root / "flaky-registry-report.md"
            registry.write_text(json.dumps([{"nodeid": "tests.test_alpha::test_flaky"}]), encoding="utf-8")

            with patch.object(
                sys,
                "argv",
                ["validate_flaky_registry.py", "--registry", str(registry), "--output", str(output)],
            ):
                self.assertEqual(validate_flaky_registry.main(), 1)

            text = output.read_text(encoding="utf-8")
            self.assertIn("- status: `fail`", text)
            self.assertIn("service_owner", text)


if __name__ == "__main__":
    unittest.main()
