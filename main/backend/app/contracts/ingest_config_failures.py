"""Typed failures owned by ingest configuration admission."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import Failure, define_failure_family


IngestConfigFailureCode = Literal["reserved_module_selection_key"]

ingest_config_failures = define_failure_family(
    "mrw.ingest_config.failure",
    get_args(IngestConfigFailureCode),
)


def ingest_config_failure(
    code: IngestConfigFailureCode,
    message: str,
    context: dict[str, object] | None = None,
) -> Failure:
    return ingest_config_failures.fail(code, message, context or {})
