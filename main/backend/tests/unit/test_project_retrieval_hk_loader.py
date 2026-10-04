"""The checked-in Hong Kong source observation stays separate from new runs."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from functorial_kit import Failure

from app.services.project_retrieval.hk_loader import _digest_json, _source_registry, _source_registry_result, build_hk_snapshot, write_hk_snapshot
from app.services.project_retrieval.mode import load_mode


_PROJECT = Path(__file__).resolve().parents[2] / "app/project_customization/projects/hk_water_investigation"


def test_build_hk_snapshot_derives_declared_sources(tmp_path: Path) -> None:
    files = {
        "分析总纲.md": "### 1 水文现场\n",
        "域.json": json.dumps({
            "域名": "水文调查", "节点类型": ["现场"], "边类型": ["关系"],
            "问题意识视角": ["物质过程"], "大纲节": ["1"], "池": ["现场池"], "档": ["A"],
        }, ensure_ascii=False),
        "来源池.md": (
            "| 源线ID | 材料与栏目 | 池 | 总纲锚点 | 大纲节 | 问题意识视角 | 拟挂节点类型 | 目标边 | 候选入口 | 词组ID | 优先级 | 状态 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            "| route:one | 栏目 | 现场池 | 1 / 水文现场 | 1 | 物质过程 | 现场 | 关系 | https://example.org | word:one | 高 | 在用 |\n"
        ),
        "初始关键词池.md": (
            "| 检索式ID | 源线ID | 词组ID | 检索式 | 大纲节 | 问题意识视角 | 目标边 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| query:one | route:one | word:one | 水文现场 | 1 | 物质过程 | 关系 |\n"
        ),
        "已固化源.md": (
            "| 源ID | 源线 | 官网名称 | URL | 栏目 | 档 | 拟挂边 | 拟挂节点 | 抓取日 | 源状态 | 快照路径 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            "| source:one | route:one | 来源 | https://example.org | 栏目 | A | 关系 | 现场 | 2026-09-19 | 已核 | snapshots/one.txt |\n"
        ),
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    snapshot = build_hk_snapshot(tmp_path, version="test-1")

    assert snapshot["version"] == "test-1"
    assert [row["query_id"] for row in snapshot["queries"]] == ["query:one"]
    assert [row["source_id"] for row in snapshot["source_registry"]] == ["source:one"]
    assert snapshot["source_snapshot"]["files"]["分析总纲.md"]["sha256"] == sha256(files["分析总纲.md"].encode()).hexdigest()


def test_build_hk_snapshot_rejects_invalid_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit safe identifier"):
        build_hk_snapshot(tmp_path, version="../escape")


def test_source_registry_core_returns_mode_failure() -> None:
    failure = _source_registry_result("no verified table", {"route:known"})
    assert isinstance(failure, Failure)
    assert failure.family == "project_retrieval.failure"
    assert failure.code == "MODE_INVALID"
    assert failure.message == "verified source table is empty"


def test_current_snapshot_contains_all_source_observations_and_exact_v1_bytes() -> None:
    current = load_mode("hk_water_investigation")
    old = load_mode("hk_water_investigation", version="1")
    assert (current["version"], old["version"]) == ("3", "1")
    old_bytes = (_PROJECT / "retrieval_mode.v1.json").read_bytes()
    assert sha256(old_bytes).hexdigest() == "37313b804770fe7b59ab0515e835a0c37065ddc556a1881708004045b8c40d6f"
    assert "source_registry" not in old
    source_files = current["source_snapshot"]["files"]
    assert set(source_files) == {
        "分析总纲.md", "域.json", "来源池.md", "初始关键词池.md", "已固化源.md"
    }
    assert source_files["已固化源.md"]["sha256"] == "4df662c408c695980178e292c4f55245f806e46892158dfae1c45c4dcfe5ecae"
    registry = current["source_registry"]
    routes = {route["route_id"] for route in current["routes"]}
    assert len(registry) == len({row["source_id"] for row in registry}) == 24
    for row in registry:
        assert row["route_ids"] and set(row["route_ids"]).issubset(routes)
        assert urlsplit(row["url"]).scheme == "https"
        assert row["status"] == "historically_verified"
        assert row["source_status_original"] == "已核"
        assert row["grade"] in current["domain_vocabulary"]["档"]
        assert not Path(row["snapshot_path"]).is_absolute()
        assert ".." not in Path(row["snapshot_path"]).parts
        assert row["verified_at"] is None  # the source table only states a capture date
        assert row["observation_sha256"] == _digest_json({k: v for k, v in row.items()
                                                            if k != "observation_sha256"})
    assert "/Users/" not in json.dumps(current, ensure_ascii=False)


@pytest.mark.parametrize(
    ("source_id", "route", "url", "snapshot_path", "error"),
    [
        ("src:bad", "route:missing", "https://example.org", "snapshots/a", "route reference"),
        ("src:bad", "route:known", "", "snapshots/a", "HTTP URL"),
        ("src:bad", "route:known", "https://example.org", "/absolute/path", "project-relative"),
        ("src:bad", "route:known", "https://example.org", "../escape", "project-relative"),
    ],
)
def test_source_observation_rejects_invalid_identity_links_and_paths(
    source_id: str, route: str, url: str, snapshot_path: str, error: str,
) -> None:
    table = ("| 源ID | 源线 | 官网名称 | URL | 栏目 | 档 | 拟挂边 | 拟挂节点 | 抓取日 | 源状态 | 快照路径 |\n"
             "|---|---|---|---|---|---|---|---|---|---|---|\n"
             f"| {source_id} | {route} | 测试 | {url} | 栏目 | A | | | 2026-09-19 | 已核 | {snapshot_path} |\n")
    with pytest.raises(ValueError, match=error):
        _source_registry(table, {"route:known"})


def test_source_observation_rejects_duplicate_id() -> None:
    header = ("| 源ID | 源线 | 官网名称 | URL | 栏目 | 档 | 拟挂边 | 拟挂节点 | 抓取日 | 源状态 | 快照路径 |\n"
              "|---|---|---|---|---|---|---|---|---|---|---|\n")
    row = "| src:one | route:known | 测试 | https://example.org | 栏目 | A | | | 2026-09-19 | 已核 | snapshots/a |\n"
    with pytest.raises(ValueError, match="duplicate"):
        _source_registry(header + row + row, {"route:known"})


def test_version_writer_preserves_old_file_bytes(tmp_path: Path) -> None:
    target = tmp_path / "retrieval_mode.json"
    old_bytes = b'{"version":"1", "manual_spacing":true}\n'
    target.write_bytes(old_bytes)
    write_hk_snapshot({"version": "2", "source_registry": []}, target)
    assert (tmp_path / "retrieval_mode.v1.json").read_bytes() == old_bytes
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == "2"


def test_version_writer_rejects_identity_replacement(tmp_path: Path) -> None:
    target = tmp_path / "retrieval_mode.json"
    target.write_text('{"version":"1","source":"old"}', encoding="utf-8")
    with pytest.raises(ValueError, match="new mode version"):
        write_hk_snapshot({"version": "1", "source": "replacement"}, target)

    historical = tmp_path / "retrieval_mode.v1.json"
    historical.write_text('{"version":"1","source":"different historical bytes"}', encoding="utf-8")
    with pytest.raises(ValueError, match="different bytes"):
        write_hk_snapshot({"version": "2", "source": "new"}, target)
