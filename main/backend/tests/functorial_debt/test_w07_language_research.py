"""Focused W07 language/research failure-family witnesses."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.successor_runtime.language.object_contracts import (
    ReturnContractRegistry,
    _failure as language_failure,
)
from app.successor_runtime.research.codec import (
    CanonicalCodecError,
    _failure as research_failure,
    canonical_json,
    dataclass_to_json,
)
from mrw_functorial_kit.core.w07_semantics import language_failures, research_failures

REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED = {
    "main/backend/app/successor_runtime/language/object_contracts.py",
    "main/backend/app/successor_runtime/research/codec.py",
}
_WITNESS = "test:test_w07_language_research_failure_boundary"


def test_w07_language_and_research_failures_are_closed_values() -> None:
    language = language_failure(
        "CONTRACT_REGISTRY_INVALID",
        "duplicate return contract ref",
        ValueError,
        site="test.language",
    )
    research = research_failure(
        "CANONICAL_ENCODING_INVALID",
        "naive datetime is not canonical",
        CanonicalCodecError,
        site="test.research",
    )
    assert isinstance(language, Failure)
    assert isinstance(research, Failure)
    assert language_failures.matches(language)
    assert research_failures.matches(research)
    assert language.context and language.context["public_exception"] == "ValueError"
    assert research.context and research.context["public_exception"] == "CanonicalCodecError"
    assert language.context and language.context["witness"] == _WITNESS
    assert research.context and research.context["witness"] == _WITNESS


def test_w07_retained_exception_abi_preserves_native_types_and_messages() -> None:
    with pytest.raises(ValueError, match="^duplicate return contract ref$"):
        ReturnContractRegistry((
            ("duplicate", object()),
            ("duplicate", object()),
        ))
    with pytest.raises(KeyError, match="^'unresolved return contract: missing'$" ):
        ReturnContractRegistry(()).resolve_required("missing")
    with pytest.raises(CanonicalCodecError, match="^naive datetime is not canonical$"):
        canonical_json(datetime(2026, 1, 1))
    with pytest.raises(TypeError, match="^expected a dataclass instance"):
        dataclass_to_json(object())


def test_w07_owned_no_throw_scan_is_closed() -> None:
    scan = scan_project(REPO_ROOT)
    assert not [
        violation
        for violation in scan.violations
        if violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
        and violation.file in OWNED
    ]
