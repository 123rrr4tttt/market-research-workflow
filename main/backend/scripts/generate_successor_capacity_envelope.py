#!/usr/bin/env python3
"""Generate one bounded local ``CapacityEnvelope.v1`` artifact.

The command is fail-closed: it requires an exact database and role, rejects
TCP and superusers in the PostgreSQL observer, validates the digest after JSON
round-trip, and only then atomically replaces the requested output file.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.pool import NullPool

from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.runtime.capacity import (
    BOUNDED_TWO_NODE_SCOPE,
    CAPACITY_ENVELOPE_SCHEMA_VERSION,
    CapacityContractError,
    CapacityEnvelope,
)
from app.successor_runtime.substrate.postgres.capacity import (
    CapacityEnvironmentGuard,
    CapacityMeasurementConfig,
    PostgresCapacityObserver,
)
from app.successor_runtime.substrate.postgres.session import create_runtime_engine

DATABASE_ENV = "SUCCESSOR_CAPACITY_DATABASE_URL"


def assert_capacity_envelope(envelope: CapacityEnvelope) -> bytes:
    """Return exact JSON bytes after all identity and scope assertions pass."""

    if envelope.schema_version != CAPACITY_ENVELOPE_SCHEMA_VERSION:
        raise CapacityContractError("capacity schema identity drifted")
    if envelope.measurement_scope != BOUNDED_TWO_NODE_SCOPE:
        raise CapacityContractError("capacity measurement scope drifted")
    if envelope.node_count != 2 or envelope.node_profile_count != 1:
        raise CapacityContractError(
            "capacity artifact is not an exact two-node baseline"
        )
    if envelope.envelope_digest != envelope.compute_digest():
        raise CapacityContractError("capacity envelope digest does not verify")
    exact = envelope.canonical_bytes()
    decoded = json.loads(exact)
    digest = decoded.pop("envelope_digest", None)
    if digest != sha256_hex(decoded):
        raise CapacityContractError("capacity JSON round-trip digest does not verify")
    if canonical_bytes({**decoded, "envelope_digest": digest}) != exact:
        raise CapacityContractError("capacity JSON is not canonical after round-trip")
    return exact + b"\n"


def write_capacity_envelope_atomic(output: Path, exact: bytes) -> None:
    """Durably replace one regular output file without a partial-write window."""

    output = output.resolve(strict=False)
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise CapacityContractError("refusing symlink capacity output")
    if output.exists() and not stat.S_ISREG(output.stat().st_mode):
        raise CapacityContractError("capacity output must be a regular file")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(exact)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def generate_capacity_envelope(
    *,
    database_url: str,
    guard: CapacityEnvironmentGuard,
    config: CapacityMeasurementConfig,
    output: Path,
) -> CapacityEnvelope:
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    try:
        envelope = PostgresCapacityObserver(engine, guard).collect(config)
        exact = assert_capacity_envelope(envelope)
        write_capacity_envelope_atomic(output, exact)
        observed = output.read_bytes()
        if observed != exact:
            raise CapacityContractError("atomic capacity artifact readback mismatch")
        return envelope
    finally:
        engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a bounded local successor CapacityEnvelope.v1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="exact output JSON path",
    )
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--expected-role", required=True)
    parser.add_argument("--allowed-project-prefix", default="p0d-capacity-")
    parser.add_argument("--allowed-schema-prefix", default="mrw_p0d_capacity_")
    parser.add_argument("--allowed-node-prefix", default="p0d-capacity-node-")
    parser.add_argument("--allowed-catalog-ref-prefix", default="p0d-capacity://")
    parser.add_argument("--claim-batch-size", type=int, default=2)
    parser.add_argument("--statement-timeout-ms", type=int, default=2_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = os.environ.get(DATABASE_ENV)
    if not database_url:
        raise SystemExit(f"{DATABASE_ENV} must contain an exact local PostgreSQL URL")
    guard = CapacityEnvironmentGuard(
        expected_database_name=args.expected_database,
        expected_role=args.expected_role,
        allowed_project_prefix=args.allowed_project_prefix,
        allowed_schema_prefix=args.allowed_schema_prefix,
        allowed_node_prefix=args.allowed_node_prefix,
        allowed_catalog_ref_prefix=args.allowed_catalog_ref_prefix,
    )
    config = CapacityMeasurementConfig(
        claim_batch_size=args.claim_batch_size,
        statement_timeout_ms=args.statement_timeout_ms,
    )
    envelope = generate_capacity_envelope(
        database_url=database_url,
        guard=guard,
        config=config,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "schema_version": envelope.schema_version,
                "measurement_scope": envelope.measurement_scope,
                "envelope_digest": envelope.envelope_digest,
                "output": str(args.output.resolve()),
                "unsupported_capacity": list(envelope.unsupported_capacity),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
