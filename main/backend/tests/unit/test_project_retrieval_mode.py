"""Project mode and preview contract, with no provider or database effects."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest
from functorial_kit import Failure

from app.services.project_retrieval import mode
from app.services.information_topology.io.retrieval import resolve_domain_vocabulary
from app.services.information_topology.modules.retrieval import make_retrieval_profile


def test_checked_in_hong_kong_mode_has_source_bound_queries() -> None:
    snapshot = mode.load_mode("hk_water_investigation")
    current = mode.current_mode(snapshot)
    assert current["project_key"] == "hk_water_investigation"
    assert current["limits"] == {"max_queries": 10, "max_materials": 20, "max_followups": 2}
    assert len(snapshot["routes"]) == 17
    assert len(current["routes"]) == 16  # reserved practice is not executable
    assert len(snapshot["queries"]) == 40
    assert len(current["queries"]) == 40
    assert all(query["expression"] for query in snapshot["queries"])
    assert all("execution_status" not in query for query in snapshot["queries"])
    assert set(snapshot["source_snapshot"]["files"]) == {
        "分析总纲.md", "域.json", "来源池.md", "初始关键词池.md", "已固化源.md",
    }
    assert current["source_registry_count"] == 24
    assert "/Users/" not in json.dumps(snapshot, ensure_ascii=False)


def test_preview_is_stable_pure_and_does_not_inherit_history() -> None:
    snapshot = mode.load_mode("hk_water_investigation")
    original = deepcopy(snapshot)
    first = mode.compile_preview(snapshot, route_id="route:supply")
    second = mode.compile_preview(snapshot, route_id="route:supply")
    assert first == second
    assert snapshot == original
    assert first["query_ids"] == ["query:01", "query:02"]
    assert first["queries"][0]["expression"] == "香港 東江水 供水協議 文件"
    assert first["topology_seed"]["attempts"] == []
    assert first["topology_seed"]["keyword_plans"][0]["execution_status"] == "not_executed"
    assert first["topology_seed"]["source_registry"]
    assert all(item["status"] == "historically_verified" for item in first["topology_seed"]["source_registry"])
    assert "topology_ref" not in first  # actual state identity is allocated by the run
    assert first["plan_id"].startswith("retrieval-plan:")
    assert [step["kind"] for step in first["steps"]][-7:] == [
        "fetch_materials", "read_materials", "judge_materials",
        "validate_evidence", "followup_search", "write_topology", "report",
    ]


def test_preview_rejects_cross_route_queries_and_budget_increase() -> None:
    snapshot = mode.load_mode("hk_water_investigation")
    with pytest.raises(ValueError, match="query_ids"):
        mode.compile_preview(snapshot, route_id="route:supply", query_ids=["query:03"])
    with pytest.raises(ValueError, match="query_ids"):
        mode.compile_preview(snapshot, route_id="route:supply", query_ids=["query:01", "query:01"])
    with pytest.raises(ValueError, match="budget"):
        mode.compile_preview(snapshot, route_id="route:supply", limits={"max_materials": 21})
    with pytest.raises(ValueError, match="inactive"):
        mode.compile_preview(snapshot, route_id="route:practice")
    narrowed = mode.compile_preview(snapshot, route_id="route:supply",
                                    query_ids=["query:02"],
                                    limits={"max_queries": 1, "max_materials": 3, "max_followups": 0})
    assert narrowed["limits"] == {"max_queries": 1, "max_materials": 3, "max_followups": 0}
    assert narrowed["plan_id"] != mode.compile_preview(snapshot, route_id="route:supply")["plan_id"]


def test_load_mode_rejects_invalid_project_key() -> None:
    with pytest.raises(ValueError, match="invalid project key"):
        mode.load_mode("../other-project")


def test_mode_core_returns_typed_failure_before_public_lift() -> None:
    snapshot = deepcopy(mode.load_mode("hk_water_investigation"))
    snapshot["source_registry"][0]["route_ids"] = ["route:missing"]
    failure = mode._validate(snapshot, "hk_water_investigation")
    assert isinstance(failure, Failure)
    assert (failure.family, failure.code) == ("project_retrieval.failure", "MODE_INVALID")
    assert "invalid route_ids" in failure.message


def test_explicit_versions_read_retained_snapshots(tmp_path, monkeypatch) -> None:
    current = mode.load_mode("hk_water_investigation")
    retained_v1 = mode.load_mode("hk_water_investigation", version="1")
    monkeypatch.setattr(mode, "_PROJECTS", tmp_path)
    project = tmp_path / "hk_water_investigation"
    project.mkdir()
    retained_v2 = deepcopy(current)
    retained_v2["version"] = "2"
    (project / "retrieval_mode.json").write_text(json.dumps(current), encoding="utf-8")
    (project / "retrieval_mode.v1.json").write_text(json.dumps(retained_v1), encoding="utf-8")
    (project / "retrieval_mode.v2.json").write_text(json.dumps(retained_v2), encoding="utf-8")
    assert mode.load_mode("hk_water_investigation", version="1") == retained_v1
    assert mode.load_mode("hk_water_investigation", version="2")["version"] == "2"
    assert mode.load_mode("hk_water_investigation")["version"] == "3"


def test_another_project_vocabulary_compiles_without_hong_kong_categories() -> None:
    snapshot = deepcopy(mode.load_mode("hk_water_investigation"))
    snapshot["project_key"] = "river_delta_study"
    snapshot["mode_id"] = "river-delta-retrieval"
    snapshot["domain_source_ref"]["ref"]["project_key"] = "river_delta_study"
    snapshot["domain_vocabulary"] = {
        "域名": "River delta", "节点类型": ["现场", "机构", "工程"],
        "边类型": ["参与", "影响"], "问题意识视角": ["河道变化"],
        "大纲节": ["A"], "池": ["地方档案"], "档": ["原始文献"],
    }
    snapshot["routes"] = [{"route_id": "delta-route", "label": "Delta records",
                            "status": "active", "query_ids": ["delta-query"],
                            "pool": "地方档案", "outline_anchor": "A",
                            "outline_sections": ["A"], "perspectives": ["河道变化"],
                            "node_types": ["机构"], "target_edges": ["影响"],
                            "source_leads": []}]
    snapshot["queries"] = [{"query_id": "delta-query", "route_id": "delta-route",
                             "expression": "delta archive"}]
    snapshot["source_registry"] = []
    preview = mode.compile_preview(snapshot, route_id="delta-route")
    vocabulary = resolve_domain_vocabulary("river_delta_study", preview["topology_seed"])
    profile = make_retrieval_profile(vocabulary)
    assert preview["query_ids"] == ["delta-query"]
    assert "node:机构" in profile.types
    assert "node:行动者" not in profile.types
