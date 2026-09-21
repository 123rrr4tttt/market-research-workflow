"""Focused authority metadata and ABI witnesses for packet W06."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import get_args, get_type_hints

from functorial_kit import scan_project, violation_key


REPO_ROOT = Path(__file__).resolve().parents[4]
PACKET_PATH = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "functorial-debt-zero-baseline-packets.v1.json"
)
WITNESS = "test:test_w06_successor_authority_metadata"
C2_TOTAL_CORE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


def _w06_derived_rows() -> list[dict[str, object]]:
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    packet_w06 = next(item for item in packet["packets"] if item["id"] == "W06")
    return [
        row
        for row in packet_w06["input_rows"]
        if row["gate"] == "derived-marked"
    ]


def _function_return(path: Path, function_name: str) -> ast.Subscript:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    assert isinstance(function.returns, ast.Subscript)
    assert ast.unparse(function.returns.value) == "Annotated"
    assert isinstance(function.returns.slice, ast.Tuple)
    assert len(function.returns.slice.elts) == 2
    return function.returns


def test_w06_successor_authority_metadata() -> None:
    rows = _w06_derived_rows()
    assert len(rows) == 54
    seen: set[tuple[str, str]] = set()

    for row in rows:
        function_name = str(row["message"]).split()[0]
        relative_path = str(row["file"])
        path = REPO_ROOT / relative_path
        annotation = _function_return(path, function_name)
        literal_node = annotation.slice.elts[1]
        assert isinstance(literal_node, ast.Subscript)
        metadata = ast.literal_eval(literal_node.slice)
        assert isinstance(metadata, str)

        if function_name == "build_serper_live_gateway":
            assert metadata.startswith(
                "kit:prepared-command effect_boundary=source_library.serper.live_provider"
            )
        else:
            assert metadata.startswith("kit:non-authoritative derived_as=")
            assert " fact_source=" in metadata

        assert metadata.endswith(WITNESS)
        seen.add((relative_path, function_name))

    assert len(seen) == len(rows) == 54


def test_w06_metadata_preserves_c1_runtime_abi() -> None:
    from app.successor_runtime.capabilities.c1_legacy_dsl import (
        build_c1_catalog,
        build_c1_contract,
        build_c1_operation_contracts,
        build_c1_registry,
    )

    contracts = build_c1_operation_contracts()
    assert [contract.ref.kind for contract in contracts] == [
        "workflow.vector_search.v1",
        "workflow.llm_call.v1",
        "workflow.join.v1",
    ]
    assert build_c1_contract("workflow.vector_search.v1") == contracts[0]
    catalog = build_c1_catalog(contracts)
    registry = build_c1_registry(contracts)
    assert catalog.entries == tuple(
        (
            contract.ref.kind,
            contract.ref.contract_version,
            contract.ref.contract_digest,
            contract.owner_capability_id,
        )
        for contract in contracts
    )
    assert (registry.catalog, registry.contracts) == (catalog, contracts)

    hints = get_type_hints(build_c1_contract, include_extras=True)
    return_metadata = get_args(hints["return"].__metadata__[0])[0]
    assert return_metadata.startswith("kit:non-authoritative derived_as=view ")
    assert "fact_source=C1_CONTRACT_KINDS+_make_contract" in return_metadata
    assert WITNESS in return_metadata


def test_w06_live_gateway_is_prepared_not_executed() -> None:
    from app.successor_runtime.capabilities.source_library_c2_3_live_provider import (
        build_serper_live_gateway,
    )

    assert build_serper_live_gateway(api_key_provider=lambda: None) is None

    captured: list[str] = []

    def provider() -> str:
        captured.append("resolve")
        return "test-key"

    gateway = build_serper_live_gateway(api_key_provider=provider)
    assert gateway is not None
    assert captured == ["resolve"]
    return_metadata = get_type_hints(build_serper_live_gateway, include_extras=True)[
        "return"
    ]
    assert get_args(return_metadata.__metadata__[0])[0] == (
        "kit:prepared-command effect_boundary=source_library.serper.live_provider "
        f"witness={WITNESS}"
    )


def test_w06_c2_total_core_failure_lifts() -> None:
    """The complete W06 no-throw packet is closed after the C7 rebind."""

    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    packet_w06 = next(item for item in packet["packets"] if item["id"] == "W06")
    expected = {
        f"{row['gate']}|{row['file']}|{row['message']}"
        for row in packet_w06["input_rows"]
        if row["gate"] == "no-throw-in-core"
    }
    actual = {violation_key(violation) for violation in scan_project(REPO_ROOT).violations}

    assert len(expected) == 44
    assert expected.isdisjoint(actual)


def test_w06_c9_total_core_failure_lifts() -> None:
    from app.successor_runtime.capabilities.source_library_worker_readback import (
        SourceLibraryWorkerObservation,
    )

    try:
        SourceLibraryWorkerObservation(
            item_key="item-1",
            plan_mode="invalid",  # type: ignore[arg-type]
            phase="planned",
            guard_decision="missing",
            observed_at="2026-09-05T00:00:00Z",
        )
    except ValueError as error:
        assert "unknown plan_mode" in str(error)
    else:
        raise AssertionError("worker readback must lift its typed C9 failure")
