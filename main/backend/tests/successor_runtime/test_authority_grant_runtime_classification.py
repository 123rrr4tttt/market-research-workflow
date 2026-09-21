"""Runtime classification preserves the exact authority-grant failure ABI."""

from __future__ import annotations

from app.successor_runtime.runtime.node import RuntimeNode
from app.successor_runtime.substrate.postgres.authority_provider import (
    CurrentAuthorityGrantUnavailable,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
)


def test_missing_current_grant_keeps_adapter_abi_and_runtime_code() -> None:
    exc = CurrentAuthorityGrantUnavailable("no current authority grant")

    assert isinstance(exc, ExactBindingConflict)
    assert RuntimeNode._error_code(exc) == "AUTHORITY_GRANT_INVALID"
