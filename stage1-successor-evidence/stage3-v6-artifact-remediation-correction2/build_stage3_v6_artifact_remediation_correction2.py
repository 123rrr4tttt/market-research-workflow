#!/usr/bin/env python3
"""Build the correction2 package as one create-only atomic directory."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[2]
HERE = Path("stage1-successor-evidence/stage3-v6-artifact-remediation-correction2")
CHECKER_PATH = ROOT / HERE / "check_stage3_v6_artifact_remediation_correction2.py"


def checker_module():
    spec = importlib.util.spec_from_file_location("stage3_correction2_checker", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("CHECKER_IMPORT")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def create_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def atomic_publish_bundle(output_dir: Path, payloads: Mapping[str, bytes]) -> None:
    """Publish all files together; an existing final directory is never replaced."""
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"create-only output exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f".{output_dir.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir(mode=0o755)
    try:
        for name, payload in sorted(payloads.items()):
            if Path(name).name != name or not name:
                raise ValueError(f"invalid bundle member name: {name}")
            create_file(staging / name, payload)
        for name, payload in payloads.items():
            if (staging / name).read_bytes() != payload:
                raise ValueError(f"staging byte drift: {name}")
        if output_dir.exists() or output_dir.is_symlink():
            raise FileExistsError(f"create-only output exists: {output_dir}")
        os.rename(staging, output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_payload_bytes(*, isolated_receipt_path: Path, isolated_expected_count: int):
    checker = checker_module()
    record, manifest, validation = checker.build_expected_payloads(
        isolated_receipt_path=isolated_receipt_path,
        isolated_expected_count=isolated_expected_count,
        root=ROOT,
    )
    record_bytes = checker.canonical(record)
    manifest_bytes = checker.canonical(manifest)
    validation_bytes = checker.canonical(validation)
    checker.validate_record(record, record)
    checker.validate_manifest(
        manifest,
        manifest,
        root=ROOT,
        virtual_files={checker.RECORD: record_bytes},
    )
    checker.validate_validation(validation, validation)
    if validation["record"]["sha256"] != checker.sha_bytes(record_bytes):
        raise ValueError("IN_MEMORY_RECORD_HASH")
    if validation["manifest"]["sha256"] != checker.sha_bytes(manifest_bytes):
        raise ValueError("IN_MEMORY_MANIFEST_HASH")
    return checker, {
        checker.RECORD.name: record_bytes,
        checker.MANIFEST.name: manifest_bytes,
        checker.VALIDATION.name: validation_bytes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    parser.add_argument("--isolated-pytest-receipt", required=True, type=Path)
    parser.add_argument("--expected-count", required=True, type=int)
    args = parser.parse_args(argv)
    checker, payloads = build_payload_bytes(
        isolated_receipt_path=args.isolated_pytest_receipt,
        isolated_expected_count=args.expected_count,
    )
    if args.write:
        atomic_publish_bundle(ROOT / checker.OUTPUT_DIR, payloads)
    else:
        expected = {
            checker.RECORD.name: (ROOT / checker.RECORD).read_bytes(),
            checker.MANIFEST.name: (ROOT / checker.MANIFEST).read_bytes(),
            checker.VALIDATION.name: (ROOT / checker.VALIDATION).read_bytes(),
        }
        if expected != payloads:
            raise ValueError("PACKAGE_BYTE_DRIFT")
        checker.check_package(
            isolated_receipt_path=args.isolated_pytest_receipt,
            isolated_expected_count=args.expected_count,
            root=ROOT,
        )
    print(
        json.dumps(
            {
                "status": "PASS_NOT_AUTHORITY",
                "authoritative": False,
                "production_release_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
