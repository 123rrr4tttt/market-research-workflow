#!/usr/bin/env python3
"""Compile one CapabilityCellSpec pilot into an exact mechanical manifest.

Missing/invalid inputs are unknown and exit 2.  ``--check`` is strictly
read-only: exact bytes exit 0, drift or a missing output exits 1, and no output
is written.  Normal generation performs an atomic write only when bytes differ.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.successor_runtime.specification import (
    CapabilityCellSpec,
    RuntimeKernelABI,
    build_manifest_bytes,
    compile_capability_spec,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class PilotInputError(RuntimeError):
    """A required input or exact binding cannot be established."""


def _load_object(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise PilotInputError(f"{label} missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotInputError(f"{label} invalid: {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise PilotInputError(f"{label} must be a JSON object: {path}")
    return value


def _resolve(root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _require_within_root(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PilotInputError(f"{label} escapes repository root: {resolved}") from exc
    return resolved


def _verify_bindings(root: Path, spec: CapabilityCellSpec) -> None:
    resolved_root = root.resolve()
    for binding in spec.exact_bindings():
        path = _resolve(resolved_root, binding.path).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError as exc:
            raise PilotInputError(
                f"exact binding escapes repository root: {path}"
            ) from exc
        if not path.is_file():
            raise PilotInputError(f"exact binding missing: {binding.path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != binding.file_sha256:
            raise PilotInputError(
                f"exact binding drift: {binding.path}: {actual} != {binding.file_sha256}"
            )


def _write_atomic_if_changed(path: Path, data: bytes) -> None:
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPOSITORY_ROOT))
    parser.add_argument("--spec", required=True)
    parser.add_argument("--runtime-kernel-abi", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    try:
        spec_path = _require_within_root(root, _resolve(root, args.spec), "spec")
        abi_path = _require_within_root(
            root,
            _resolve(root, args.runtime_kernel_abi),
            "runtime kernel ABI",
        )
        output_path = _require_within_root(
            root,
            _resolve(root, args.output),
            "output",
        )
        spec = CapabilityCellSpec.from_dict(_load_object(spec_path, "spec"))
        abi = RuntimeKernelABI.from_dict(_load_object(abi_path, "runtime kernel ABI"))
        _verify_bindings(root, spec)
        expected = build_manifest_bytes(compile_capability_spec(spec, abi))
    except (PilotInputError, TypeError, ValueError, KeyError) as exc:
        print(f"UNKNOWN: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if not output_path.is_file() or output_path.read_bytes() != expected:
            print(f"DRIFT: {output_path}", file=sys.stderr)
            return 1
        print(f"MATCH: {output_path}")
        return 0
    _write_atomic_if_changed(output_path, expected)
    print(f"WROTE: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
