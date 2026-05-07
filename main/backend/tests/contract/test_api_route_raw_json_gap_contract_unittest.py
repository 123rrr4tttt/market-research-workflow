from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract


class ApiRouteRawJsonGapContractTestCase(unittest.TestCase):
    def test_route_functions_do_not_return_raw_dict_or_list_literals(self):
        api_dir = Path(__file__).resolve().parents[2] / "app" / "api"
        offenders: list[str] = []

        for path in sorted(api_dir.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not any(
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in {"get", "post", "put", "delete", "patch"}
                    for dec in node.decorator_list
                ):
                    continue
                for sub in ast.walk(node):
                    if not isinstance(sub, ast.Return) or sub.value is None:
                        continue
                    if isinstance(sub.value, (ast.Dict, ast.List)):
                        offenders.append(f"{path.relative_to(api_dir.parent)}:{node.name}:{sub.lineno}")

        self.assertEqual(
            offenders,
            [],
            msg="Public API routes should not return raw dict/list literals directly",
        )


if __name__ == "__main__":
    unittest.main()
