#!/usr/bin/env python3
"""Guardrail for API-layer standards.

Wave0 behavior:
- Allow existing baseline imports listed in allowlist.
- Fail only when new direct imports from ``..models`` are introduced.
- Allow existing baseline ``raise HTTPException(..., detail=...)`` in API layer.
- Fail only when new such raises are introduced.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
API_DIR = BACKEND_ROOT / "app" / "api"
ALLOWLIST_PATH = BACKEND_ROOT / "docs" / "API_LAYER_MODEL_IMPORT_ALLOWLIST.txt"
HTTP_EXCEPTION_ALLOWLIST_PATH = (
    BACKEND_ROOT / "docs" / "API_LAYER_HTTP_EXCEPTION_DETAIL_ALLOWLIST.txt"
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


def _collect_http_exception_detail_raises() -> set[str]:
    findings: set[str] = set()

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

            call_text = ast.unparse(node.exc).replace("\n", " ").strip()
            findings.add(f"{file_path.name}:L{node.lineno}|raise {call_text}")

    return findings


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


def main() -> int:
    model_detected = _collect_model_imports()
    model_allowed = _load_allowlist(ALLOWLIST_PATH)
    http_detected = _collect_http_exception_detail_raises()
    http_allowed = _load_allowlist(HTTP_EXCEPTION_ALLOWLIST_PATH)

    model_unexpected = sorted(model_detected - model_allowed)
    model_stale = sorted(model_allowed - model_detected)
    http_unexpected = sorted(http_detected - http_allowed)
    http_stale = sorted(http_allowed - http_detected)

    print(f"Scanned {len(list(API_DIR.glob('*.py')))} API files in {API_DIR}")
    print(f"Detected {len(model_detected)} direct '..models' imports")
    print(
        "Detected "
        f"{len(http_detected)} API raises of HTTPException(..., detail=...)"
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
            print(f"  - {item}")
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
