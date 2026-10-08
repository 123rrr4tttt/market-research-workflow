"""W01 witnesses for typed contract failures and preserved Pydantic ABI."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure
from pydantic import ValidationError

from app.contracts.schemas import writing


REPO_ROOT = Path(__file__).resolve().parents[4]


def _assert_failure_context(failure: Failure, *, family: str, code: str) -> None:
    assert failure.family == family
    assert failure.code == code
    context = dict(failure.context or {})
    for key in ("owner", "operation", "site", "public_exception", "public_message", "witness"):
        assert context.get(key)
    assert context["public_exception"] == "ValueError"
    assert context["public_message"] == failure.message
    assert context["witness"] == "test:test_w01_contract_failures"


def test_w01_writing_query_core_failure() -> None:
    failure = writing._normalize_writing_query("\t", operation="KeywordCardRequest.query")

    assert isinstance(failure, Failure)
    _assert_failure_context(
        failure,
        family="writing.request.contract_failure",
        code="query_required",
    )


@pytest.mark.parametrize("model", [writing.KeywordCardRequest, writing.SuggestRequest])
def test_w01_writing_pydantic_lift_preserves_validation_error(model: type[object]) -> None:
    with pytest.raises(ValidationError, match=r"query is required"):
        model(query=" ")


@pytest.mark.parametrize(
    "relative_path",
    (
        "main/backend/app/contracts/schemas/writing.py",
    ),
)
def test_w01_each_contract_file_has_one_pydantic_lift_raise(relative_path: str) -> None:
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    raises = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Raise)]
    assert len(raises) == 1
