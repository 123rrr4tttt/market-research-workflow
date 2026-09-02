#!/usr/bin/env python3
"""Generate the pilot RuntimeKernelABI semantic artifact deterministically."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.successor_runtime.specification.capability_cell_spec import (
    canonical_json_bytes,
)
from app.successor_runtime.specification.runtime_kernel_abi import RuntimeKernelABI


def build_bytes() -> bytes:
    abi = RuntimeKernelABI(
        program_protocol_version="mrw.successor.program.v1",
        plan_protocol_version="mrw.successor.execution-plan.v1",
        handler_binding_protocol_version="mrw.successor.handler-binding.v1",
        assignment_protocol_version="mrw.successor.runtime-assignment.v1",
        reducer_protocol_version="mrw.successor.unified-reducer.v1",
        work_item_protocol_version="mrw.successor.runtime-work-item.v1",
    ).with_digest()
    return canonical_json_bytes(abi.to_dict()) + b"\n"


def _write_if_changed(output: Path, expected: bytes) -> None:
    if output.exists() and output.read_bytes() == expected:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=output.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        output.chmod(0o644)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = build_bytes()
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != expected:
            return 1
        return 0
    _write_if_changed(args.output, expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
