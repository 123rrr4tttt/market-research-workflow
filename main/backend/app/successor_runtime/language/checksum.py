"""Canonical codec and digest surface for the program language layer.

The implementation lives in ``app.successor_runtime.research.codec`` so that
research objects can use it without an outward dependency.  This module is the
language-facing re-export and adds no lossy default coercion.
"""

from app.successor_runtime.research.codec import (
    CanonicalCodecError,
    UnsupportedCanonicalValueError,
    canonical_bytes,
    canonical_json,
    dataclass_to_json,
    digest_dataclass,
    encode,
    finalize_digest,
    is_sha256_hex,
    sha256_hex,
)

__all__ = [
    "CanonicalCodecError",
    "UnsupportedCanonicalValueError",
    "canonical_bytes",
    "canonical_json",
    "dataclass_to_json",
    "digest_dataclass",
    "encode",
    "finalize_digest",
    "is_sha256_hex",
    "sha256_hex",
]
