from __future__ import annotations

import importlib.util
import json
import re
import sys
import ast
import shlex
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

REPO_ROOT = Path(__file__).resolve().parents[2]
W11_WITNESS = "test:test_w11_non_authoritative_metadata"
C16_WITNESS = "test:test_INVARIANT__c16_business_cli_authority_metadata"


def _c16_case_keys() -> set[tuple[str, str]]:
    """Read the C16 ownership matrix so overlapping W11 rows keep their owner."""

    path = REPO_ROOT / "tests/functorial_debt/test_c16_business_cli_authority.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    cases_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CASES" for target in node.targets)
    )
    cases = ast.literal_eval(cases_node.value)
    return {(file_name, function_name) for file_name, function_name, _ in cases}


def _function(file_name: str, function_name: str):
    path = REPO_ROOT / file_name
    module_name = file_name.removesuffix(".py").replace("/", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, function_name)


def _assert_direct_annotated_return(file_name: str, function_name: str) -> None:
    source = (REPO_ROOT / file_name).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=file_name)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    assert isinstance(function.returns, ast.Subscript)
    assert isinstance(function.returns.value, ast.Name)
    assert function.returns.value.id == "Annotated"


def test_w11_non_authoritative_metadata() -> None:
    packet_document = json.loads(
        (REPO_ROOT / "docs/governance/functorial-debt-zero-baseline-packets.v1.json").read_text(
            encoding="utf-8"
        )
    )
    packet = next(packet for packet in packet_document["packets"] if packet["id"] == "W11")
    cases = {row["key"]: row for row in packet["input_rows"]}
    assert len(cases) == 33
    c16_case_keys = _c16_case_keys()

    for baseline_key, row in cases.items():
        function_name = row["key"].split("|")[2].split(" ", 1)[0]
        _assert_direct_annotated_return(row["file"], function_name)
        function = _function(row["file"], function_name)
        return_hint = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_hint) is Annotated

        value, annotation = get_args(return_hint)
        assert value is not None
        assert isinstance(annotation, str)
        expected_witness = (
            C16_WITNESS
            if (row["file"], function_name) in c16_case_keys
            else W11_WITNESS
        )
        assert f"witness={expected_witness}" in annotation

        tokens = shlex.split(annotation)
        assert tokens[0] in {"kit:non-authoritative", "kit:prepared-command"}
        fields = dict(token.split("=", 1) for token in tokens[1:])
        expected_fields = (
            {"derived_as", "fact_source", "witness"}
            if tokens[0] == "kit:non-authoritative"
            else {"effect_boundary", "witness"}
        )
        assert set(fields) == expected_fields

        if function_name == "build_url":
            assert annotation.startswith("kit:prepared-command ")
            assert fields["effect_boundary"]
        else:
            assert annotation.startswith("kit:non-authoritative ")
            kind = re.search(r"derived_as=([a-z_]+)", annotation)
            fact_source = re.search(r"fact_source=([^ ]+)", annotation)
            assert kind is not None
            assert kind.group(1) in {"view", "preflight", "generated_evidence"}
            assert fact_source is not None and fact_source.group(1)

        assert baseline_key.startswith(f"derived-marked|{row['file']}|")
