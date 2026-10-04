from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.services.agent_core.contracts import CoreToolResult
from app.services.agent_core.functorial import run as run_module
from app.services.agent_core.functorial import workflow as workflow_module
from app.services.agent_core.functorial.contracts import OperatorValidationError
from app.services.agent_core.functorial.operator import OperatorSpec, _operator_from_core_spec
from app.services.agent_core.functorial.registry import CatalogLoadError, FunctorialCatalog


class _Registry:
    def __init__(self, results: list[CoreToolResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def get(self, operator_id: str) -> object:
        return object() if operator_id in {"first", "second"} else None

    def execute_tool(self, *, tool_call: Any, **_: Any) -> CoreToolResult:
        self.calls.append(dict(tool_call.arguments))
        return self.results.pop(0)


def _result(
    tool: str,
    status: str = "completed",
    *,
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    retry_hint: str | None = None,
) -> CoreToolResult:
    return CoreToolResult(
        call_id="call",
        tool_name=tool,
        status=status,  # type: ignore[arg-type]
        model_summary=f"{tool}:{status}",
        structured_content=data or {},
        error=error,
        retry_hint=retry_hint,
    )


def test_ORDERED_COMPOSITION__stored_program_routes_previous_output(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = _Registry(
        [
            _result("first", data={"value": "from-first"}),
            _result("second", data={"value": "from-second"}),
        ]
    )
    workflow = {
        "program": {
            "nodes": [
                {"kind": "operator", "ref": "operator:first"},
                {"kind": "operator", "ref": "operator:second"},
            ]
        },
        # Runtime must not reinterpret this second representation.
        "steps": ["operator:ignored"],
    }
    monkeypatch.setattr(run_module, "AgentSessionService", lambda: object())
    monkeypatch.setattr(
        run_module,
        "build_project_core_tool_registry",
        lambda **_: registry,
    )
    monkeypatch.setattr(run_module, "_resolve_session_id", lambda *_: "session")
    monkeypatch.setattr(
        run_module._fcatalog,
        "get",
        lambda _collection, workflow_id: workflow if workflow_id == "wf" else None,
    )

    output = run_module.run_workflow("wf", {"value": "initial"}, "project")

    assert registry.calls == [{"value": "initial"}, {"value": "from-first"}]
    assert output["status"] == "completed"
    assert output["executed"] is True
    assert output["authority"] == "PROJECTION_ONLY"


def test_FAILURE_PRESERVED__terminal_operator_stops_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = _Registry(
        [
            _result(
                "first",
                status="failed",
                error={"code": "UPSTREAM"},
                retry_hint="inspect provider",
            )
        ]
    )
    workflow = {
        "program": {
            "nodes": [
                {"kind": "operator", "ref": "operator:first"},
                {"kind": "operator", "ref": "operator:second"},
            ]
        }
    }
    monkeypatch.setattr(run_module, "AgentSessionService", lambda: object())
    monkeypatch.setattr(
        run_module,
        "build_project_core_tool_registry",
        lambda **_: registry,
    )
    monkeypatch.setattr(run_module, "_resolve_session_id", lambda *_: "session")
    monkeypatch.setattr(
        run_module._fcatalog,
        "get",
        lambda _collection, workflow_id: workflow if workflow_id == "wf" else None,
    )

    output = run_module.run_workflow("wf", {}, "project")

    assert len(registry.calls) == 1
    assert output["status"] == "failed"
    assert output["executed"] is False
    assert output["failure"]["code"] == "OPERATOR_FAILED"
    assert output["steps"][0]["error"] == {"code": "UPSTREAM"}
    assert output["steps"][0]["retry_hint"] == "inspect provider"


def test_INVARIANT__operator_schema_derives_from_core_spec() -> None:
    core_spec = type(
        "CoreSpec",
        (),
        {
            "name": "operator.demo",
            "title": "Demo",
            "input_schema": {"type": "object", "properties": {"a": {}}},
            "output_schema": {"type": "object", "properties": {"b": {}}},
            "risk": "write_shared",
        },
    )()
    projected = _operator_from_core_spec(core_spec)
    assert projected.input_schema == core_spec.input_schema
    assert projected.output_schema == core_spec.output_schema
    assert projected.risk == "write_shared"


def test_INVARIANT__operator_risk_rejects_unknown_value() -> None:
    core_spec = type(
        "CoreSpec",
        (),
        {
            "name": "operator.bad",
            "title": None,
            "input_schema": {},
            "output_schema": {},
            "risk": "unknown",
        },
    )()
    with pytest.raises(OperatorValidationError, match="unsupported operator risk"):
        _operator_from_core_spec(core_spec)


def test_INVARIANT__catalog_construction_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    catalog = FunctorialCatalog(data_root=tmp_path / "functorial")
    assert not (tmp_path / "functorial").exists()

    spec = OperatorSpec(
        operator_id="demo",
        name="Demo",
        input_schema={},
        output_schema={},
        impl_ref="test",
        risk="read_only",
    )
    first = catalog.upsert_operator("demo", spec.to_dict())
    second = catalog.upsert_operator("demo", spec.to_dict())
    assert first["revision"] == 1
    assert second["revision"] == 2

    path = tmp_path / "functorial" / "operators.jsonl"
    path.write_text("{ malformed\n", encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="malformed functorial catalog line"):
        FunctorialCatalog(data_root=tmp_path / "functorial")


def test_ORDERED_COMPOSITION__workflow_program_flattens_motif_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class Catalog:
        def __init__(self) -> None:
            self.records: dict[tuple[str, str], dict[str, Any]] = {}

        def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
            return self.records.get((collection, record_id))

        def upsert_workflow(self, record_id: str, spec: dict[str, Any]) -> dict[str, Any]:
            self.records[("workflows", record_id)] = dict(spec)
            return dict(spec)

    catalog = Catalog()
    schema = {"type": "object", "properties": {}}
    catalog.records[
        ("operators", "one")
    ] = {"input_schema": schema, "output_schema": schema}
    catalog.records[
        ("operators", "two")
    ] = {"input_schema": schema, "output_schema": schema}
    catalog.records[("motifs", "chain")] = {
        "composition": ("operator:one", "operator:two"),
        "input_schema": schema,
        "output_schema": schema,
    }
    monkeypatch.setattr(workflow_module, "catalog", catalog)
    monkeypatch.setattr(workflow_module, "ensure_operator_catalog", lambda: None)

    spec = workflow_module.build_workflow_program(
        "wf", "WF", ["motif:chain"], laws=["identity"]
    )

    assert spec.steps == ("motif:chain",)
    assert [node["ref"] for node in spec.program["nodes"]] == [
        "operator:one",
        "operator:two",
    ]
    assert all(node["kind"] == "operator" for node in spec.program["nodes"])


def test_authoring_capability_sources_preserve_original_loop_semantics() -> None:
    from app.services.agent_core.authoring_tools import (
        authoring_capability_sources,
    )

    capabilities = [
        {"capability_id": "unrelated.read"},
        {
            "capability_id": "report.generate",
            "name": "Generate Report",
            "description": "Generate a durable report draft.",
            "approval_level": "explicit_user_request",
            "concurrency_class": "write_shared",
            "risks": ["shared_write"],
        },
        {
            "capability_id": "workflow_graph.run",
            "name": "Run Workflow",
            "description": "Start a governed workflow graph.",
            "approval_level": "explicit_user_request",
            "concurrency_class": "write_shared",
            "risks": ["shared_write"],
        },
    ]

    sources = authoring_capability_sources(object(), capabilities)

    assert [source.tool_spec.name for source in sources] == [
        "report.generate",
        "workflow_graph.run",
    ]
    report_spec = sources[0].tool_spec
    workflow_spec = sources[1].tool_spec
    assert report_spec.source == "legacy_adapter"
    assert report_spec.permission == "explicit_user_request"
    assert report_spec.risk == "write_shared"
    assert report_spec.concurrency == "serial"
    assert report_spec.input_schema["required"] == ["topic", "output_path"]
    assert workflow_spec.input_schema["required"] == ["graph_id", "inputs"]
    assert sources[0].executor_ref == "report.generate"
    assert sources[1].executor_ref == "workflow_graph.run"
