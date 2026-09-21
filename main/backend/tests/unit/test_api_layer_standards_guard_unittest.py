from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest


_CHECKER_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_api_layer_imports.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "check_api_layer_imports", _CHECKER_PATH
)
checker = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(checker)


class APILayerStandardsGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        root = Path(self._temporary.name)
        self.api_dir = root / "app" / "api"
        self.api_dir.mkdir(parents=True)
        self.model_allowlist = root / "docs" / "models.txt"
        self.http_allowlist = root / "docs" / "http.txt"
        self.model_allowlist.parent.mkdir()
        self._patch(checker, "API_DIR", self.api_dir)
        self._patch(checker, "ALLOWLIST_PATH", self.model_allowlist)
        self._patch(checker, "HTTP_EXCEPTION_ALLOWLIST_PATH", self.http_allowlist)

    def _patch(self, module: object, name: str, value: object) -> None:
        original = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(lambda: setattr(module, name, original))

    def _run(self) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = checker.main()
        return status, output.getvalue()

    def _write_api(self, relative: str, source: str) -> None:
        path = self.api_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def _write_http_allowlist(self, *rows: str) -> None:
        self.http_allowlist.write_text(
            "\n".join(("# baseline", *rows)) + "\n", encoding="utf-8"
        )

    def test_line_drift_and_source_layout_do_not_create_new_finding(self) -> None:
        self._write_api(
            "alpha.py",
            "\n".join(
                (
                    "def handler():",
                    "    return None",
                    "",
                    "",
                    "raise HTTPException(",
                    "    status_code=400,",
                    "    detail=message,",
                    ")",
                )
            )
            + "\n",
        )
        self._write_http_allowlist(
            "alpha.py:L2|raise HTTPException(status_code=400, detail=message)"
        )

        status, output = self._run()

        self.assertEqual(status, 0)
        self.assertIn("No new API-layer HTTPException", output)

    def test_new_call_and_new_file_fail_with_line_as_diagnostic_only(self) -> None:
        self._write_api(
            "alpha.py",
            "raise HTTPException(status_code=400, detail=message)\n",
        )
        self._write_api(
            "beta.py",
            "raise HTTPException(status_code=401, detail=changed)\n",
        )
        self._write_http_allowlist(
            "alpha.py:L91|raise HTTPException(status_code=400, detail=message)"
        )

        status, output = self._run()

        self.assertEqual(status, 1)
        self.assertNotIn("alpha.py:L91", output)
        self.assertIn(
            "beta.py|raise HTTPException(status_code=401, detail=changed)", output
        )

    def test_second_identical_call_exceeds_semantic_budget(self) -> None:
        self._write_api(
            "alpha.py",
            (
                "raise HTTPException(status_code=400, detail=message)\n"
                "raise HTTPException(status_code=400, detail=message)\n"
            ),
        )
        self._write_http_allowlist(
            "alpha.py:L2|raise HTTPException(status_code=400, detail=message)"
        )

        status, output = self._run()

        self.assertEqual(status, 1)
        self.assertIn(
            "alpha.py|raise HTTPException(status_code=400, detail=message)", output
        )
        self.assertIn("(source L1)", output)
        self.assertIn("(source L2)", output)

    def test_changed_call_fails_without_hiding_allowed_baseline(self) -> None:
        self._write_api(
            "alpha.py",
            (
                "raise HTTPException(status_code=400, detail=message)\n"
                "raise HTTPException(status_code=400, detail=changed)\n"
            ),
        )
        self._write_http_allowlist(
            "alpha.py:L1|raise HTTPException(status_code=400, detail=message)"
        )

        status, output = self._run()

        self.assertEqual(status, 1)
        self.assertIn(
            "alpha.py|raise HTTPException(status_code=400, detail=changed)", output
        )
        self.assertNotIn("detail=message) (source", output)

    def test_stale_allowance_is_reported_as_nonblocking(self) -> None:
        self._write_api(
            "alpha.py",
            "raise HTTPException(status_code=400, detail=message)\n",
        )
        self._write_http_allowlist(
            "alpha.py:L1|raise HTTPException(status_code=400, detail=message)",
            "gone.py:L9|raise HTTPException(status_code=404, detail=removed)",
        )

        status, output = self._run()

        self.assertEqual(status, 0)
        self.assertIn("Stale HTTPException allowlist entries", output)
        self.assertIn("gone.py|raise HTTPException", output)

    def test_malformed_allowance_fails_closed(self) -> None:
        self._write_api(
            "alpha.py",
            "raise HTTPException(status_code=400, detail=message)\n",
        )
        self.http_allowlist.write_text(
            "alpha.py|raise HTTPException(status_code=400, detail=message)\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "Malformed HTTPException allowance"):
            self._run()

        self.http_allowlist.write_text(
            "alpha.py:L1|raise message\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "allowance is not a call"):
            self._run()


if __name__ == "__main__":
    unittest.main()
