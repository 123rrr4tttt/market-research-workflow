#!/usr/bin/env python3
# ruff: noqa: TRY003, TRY004
"""Guardrail for API-layer standards.

Wave0 behavior:
- Allow existing baseline imports listed in allowlist.
- Fail only when new direct imports from ``..models`` are introduced.
- Allow existing baseline ``raise HTTPException(..., detail=...)`` in API layer.
- Fail only when new such raises are introduced.
"""

from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
API_DIR = BACKEND_ROOT / "app" / "api"
ALLOWLIST_PATH = BACKEND_ROOT / "docs" / "API_LAYER_MODEL_IMPORT_ALLOWLIST.txt"
HTTP_EXCEPTION_ALLOWLIST_PATH = (
    BACKEND_ROOT / "docs" / "API_LAYER_HTTP_EXCEPTION_DETAIL_ALLOWLIST.txt"
)
_HTTP_ALLOWLIST_LINE_RE = re.compile(
    r"^(?P<filename>[^:]+):L(?P<line>\d+)\|(?P<entry>raise .+)$"
)


def _normalize_aliases(names: list[ast.alias]) -> str:
    parts = []
    for alias in names:
        if alias.asname:
            parts.append(f"{alias.name} as {alias.asname}")
        else:
            parts.append(alias.name)
    return ", ".join(sorted(parts))


def _collect_model_imports() -> set[str]:
    findings: set[str] = set()

    for file_path in sorted(API_DIR.glob("*.py")):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level != 2 or not node.module:
                continue
            if node.module != "models" and not node.module.startswith("models."):
                continue

            imports_text = _normalize_aliases(node.names)
            findings.add(
                f"{file_path.name}|from ..{node.module} import {imports_text}"
            )

    return findings


def _is_http_exception_func(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id == "HTTPException"
    if isinstance(func, ast.Attribute):
        return func.attr == "HTTPException"
    return False


def _normalized_http_exception_call(call: ast.Call) -> str:
    """Return the stable, source-layout-independent AST spelling of a call."""

    return ast.unparse(call).replace("\n", " ").strip()


def _http_exception_semantic_key(filename: str, call: ast.Call) -> str:
    return f"{filename}|raise {_normalized_http_exception_call(call)}"


def _collect_http_exception_detail_raises() -> tuple[
    Counter[str], dict[str, list[tuple[int, str]]]
]:
    findings: Counter[str] = Counter()
    diagnostics: dict[str, list[tuple[int, str]]] = {}

    for file_path in sorted(API_DIR.glob("*.py")):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            if not isinstance(node.exc, ast.Call):
                continue
            if not _is_http_exception_func(node.exc.func):
                continue

            has_detail = any(keyword.arg == "detail" for keyword in node.exc.keywords)
            if not has_detail:
                continue

            key = _http_exception_semantic_key(file_path.name, node.exc)
            findings[key] += 1
            diagnostics.setdefault(key, []).append((node.lineno, key))

    return findings, diagnostics


def _load_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()

    entries: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line)

    return entries


def _load_http_exception_allowlist(
    path: Path,
) -> tuple[Counter[str], dict[str, list[tuple[int, str]]]]:
    """Project historical line-pinned rows to stable semantic allowances.

    The checked-in text remains the immutable historical record.  ``L`` values
    are parsed only so validation errors and diagnostic output can identify the
    source row; they are deliberately absent from the comparison key.
    """

    if not path.exists():
        return Counter(), {}

    allowances: Counter[str] = Counter()
    diagnostics: dict[str, list[tuple[int, str]]] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _HTTP_ALLOWLIST_LINE_RE.fullmatch(line)
        if not match:
            raise ValueError(
                f"Malformed HTTPException allowance at {path}:L{line_number}: {line}"
            )  # noqa: TRY003

        filename = match.group("filename")
        entry = match.group("entry")
        try:
            expression = ast.parse(entry.removeprefix("raise "), mode="eval")
        except SyntaxError as exc:
            raise ValueError(
                f"Malformed HTTPException allowance call at {path}:L{line_number}: {line}"
            ) from exc  # noqa: TRY003
        if not isinstance(expression.body, ast.Call):
            raise ValueError(
                f"HTTPException allowance is not a call at {path}:L{line_number}: {line}"
            )  # noqa: TRY003, TRY004
        call = expression.body
        if not _is_http_exception_func(call.func) or not any(
            keyword.arg == "detail" for keyword in call.keywords
        ):
            raise ValueError(
                f"HTTPException allowance is not HTTPException(detail=...) at "
                f"{path}:L{line_number}: {line}"
            )  # noqa: TRY003

        key = _http_exception_semantic_key(filename, call)
        allowances[key] += 1
        diagnostics.setdefault(key, []).append((line_number, line))

    return allowances, diagnostics


def _multiset_difference(left: Counter[str], right: Counter[str]) -> Counter[str]:
    return left - right


def main() -> int:
    model_detected = _collect_model_imports()
    model_allowed = _load_allowlist(ALLOWLIST_PATH)
    http_detected, http_source_lines = _collect_http_exception_detail_raises()
    http_allowed, _http_allowlist_lines = _load_http_exception_allowlist(
        HTTP_EXCEPTION_ALLOWLIST_PATH
    )

    model_unexpected = sorted(model_detected - model_allowed)
    model_stale = sorted(model_allowed - model_detected)
    http_unexpected = sorted(_multiset_difference(http_detected, http_allowed))
    http_stale = sorted(_multiset_difference(http_allowed, http_detected))

    print(f"Scanned {len(list(API_DIR.glob('*.py')))} API files in {API_DIR}")
    print(f"Detected {len(model_detected)} direct '..models' imports")
    print(
        "Detected "
        f"{sum(http_detected.values())} API raises of HTTPException(..., detail=...) "
        f"({len(http_detected)} distinct semantic calls)"
    )

    if model_unexpected:
        print("\nUnexpected API-layer direct model imports found:")
        for item in model_unexpected:
            print(f"  - {item}")
        print("\nAction: route through service layer or explicitly update allowlist with review.")
    else:
        print("\nNo new API-layer direct model imports found.")
    if model_stale:
        print("Stale model-import allowlist entries (non-blocking):")
        for item in model_stale:
            print(f"  - {item}")

    if http_unexpected:
        print("\nUnexpected API-layer HTTPException(detail=...) raises found:")
        for item in http_unexpected:
            occurrences = http_source_lines.get(item, ())
            for occurrence, _diagnostic in occurrences:
                print(f"  - {item} (source L{occurrence})")
        print(
            "\nAction: prefer structured API envelope; "
            "if needed, explicitly update allowlist with review."
        )
    else:
        print("\nNo new API-layer HTTPException(detail=...) raises found.")
    if http_stale:
        print("Stale HTTPException allowlist entries (non-blocking):")
        for item in http_stale:
            print(f"  - {item}")

    if model_unexpected or http_unexpected:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
