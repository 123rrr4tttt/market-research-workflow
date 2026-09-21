"""Registration projection for shared family generator fragments.

The P3 and P4 fragment generators remain the authoritative producers.  These
codecs only bind two existing on-disk fragment objects to the kit registry and
carry a mapping through unchanged; they neither regenerate nor rewrite the
persisted fragment bytes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, get_args

from functorial_kit import define_codec, define_failure_family


SharedFamilyGeneratorFailureCode = Literal[
    "config_invalid",
    "authority_enabled",
    "path_escape",
    "input_invalid",
    "binding_missing",
    "fragment_invariant_invalid",
    "nondeterministic_output",
    "check_drift",
    "check_unknown",
]

shared_family_generator_failures = define_failure_family(
    "shared.family.generator.failure",
    get_args(SharedFamilyGeneratorFailureCode),
)


def _parse_fragment(value: Mapping[str, Any]) -> Mapping[str, Any]:
    identity_fields = ("family", "fragment_id", "phase", "schema", "status")
    missing = [field for field in identity_fields if not isinstance(value.get(field), str)]
    if missing:
        return shared_family_generator_failures.fail(
            "fragment_invariant_invalid",
            "fragment identity fields must be strings",
            {"fields": missing},
        )
    return value


shared_family_p3_fragment_codec = define_codec(
    name="shared.family.generator.p3_fragment",
    discriminant="mrw.functorial_successor.p3_fragment.v1",
    discriminant_key="schema",
    keys=(
        "authority",
        "cells",
        "content_digest",
        "family",
        "fragment_id",
        "implementation_bindings",
        "open_findings",
        "phase",
        "schema",
        "source_bindings",
        "status",
        "test_bindings",
    ),
    parse=_parse_fragment,
    to_wire=lambda fragment: fragment,
)

shared_family_p4_fragment_codec = define_codec(
    name="shared.family.generator.p4_fragment",
    discriminant="mrw.functorial_successor.p4_fragment.v1",
    discriminant_key="schema",
    keys=(
        "authority",
        "cells",
        "content_digest",
        "family",
        "fragment_id",
        "implementation_bindings",
        "lifecycle_state",
        "open_findings",
        "phase",
        "schema",
        "source_bindings",
        "status",
        "test_bindings",
    ),
    parse=_parse_fragment,
    to_wire=lambda fragment: fragment,
)


__all__ = [
    "shared_family_generator_failures",
    "shared_family_p3_fragment_codec",
    "shared_family_p4_fragment_codec",
]
