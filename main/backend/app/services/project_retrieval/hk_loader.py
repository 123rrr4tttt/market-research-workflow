"""Explicit authoring-time import of the Hong Kong research setup.

This module is only used when a maintainer refreshes the checked-in mode file.
The application reads that file through :mod:`mode` and never needs the source
directory from the author's workstation.
"""
# ruff: noqa: TRY003

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Annotated, Any
from urllib.parse import urlsplit

from functorial_kit import Failure

from .failures import retrieval_failure


_NAMES = ("分析总纲.md", "域.json", "来源池.md", "初始关键词池.md", "已固化源.md")


def _rejected(message: str) -> Failure:
    return retrieval_failure(
        "MODE_INVALID", message, site="hk_loader.authored_mode",
    )


def _rows(markdown: str, first_column: str) -> list[dict[str, str]]:
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] == first_column:
            header = cells
            continue
        if header and len(cells) == len(header) and cells[0] and not cells[0].startswith("---"):
            rows.append(dict(zip(header, cells, strict=True)))
    return rows


def _multi(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[；;]", value) if part.strip()]


def _headline(anchor: str) -> str:
    return anchor.split(" / ", 1)[-1]


def _digest_json(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _snapshot_path(value: str) -> str | Failure:
    """Keep a source-owned path as a relative reference, never a host path."""
    path = Path(value)
    if (not value or path.is_absolute() or "\\" in value
            or any(part in (".", "..", "") for part in value.split("/"))):
        return _rejected("source snapshot path must be project-relative")
    return path.as_posix()


def _source_registry_result(markdown: str, route_ids: set[str]) -> list[dict[str, Any]] | Failure:
    rows = _rows(markdown, "源ID")
    if not rows:
        return _rejected("verified source table is empty")
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        source_id = row["源ID"]
        references = _multi(row["源线"])
        url = row["URL"].strip()
        parts = urlsplit(url)
        if not source_id or source_id in seen:
            return _rejected(f"duplicate or empty source ID: {source_id}")
        if not references or len(references) != len(set(references)) or not set(references).issubset(route_ids):
            return _rejected(f"source {source_id} has an invalid route reference")
        if parts.scheme not in {"http", "https"} or not parts.netloc or any(char.isspace() for char in url):
            return _rejected(f"source {source_id} needs a nonempty HTTP URL")
        if row["源状态"] != "已核":
            return _rejected(f"source {source_id} is not a verified source observation")
        seen.add(source_id)
        snapshot_path = _snapshot_path(row["快照路径"])
        if isinstance(snapshot_path, Failure):
            return snapshot_path
        record = {
            "source_id": source_id, "route_ids": references, "name": row["官网名称"],
            "url": url, "status": "historically_verified", "source_status_original": row["源状态"],
            "grade": row["档"], "snapshot_path": snapshot_path,
            # The table gives a capture date, not a verification timestamp.
            "captured_on": row["抓取日"], "verified_at": None,
            "column": row["栏目"], "target_edges": _multi(row["拟挂边"]),
            "target_nodes": _multi(row["拟挂节点"]),
        }
        record["observation_sha256"] = _digest_json(record)
        sources.append(record)
    return sources


def _source_registry(markdown: str, route_ids: set[str]) -> list[dict[str, Any]]:
    """Retain the direct validation API used by authoring-time callers."""
    result = _source_registry_result(markdown, route_ids)
    if isinstance(result, Failure):
        # kit:boundary owner=project_retrieval.hk_loader.source_registry class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_source_observation_rejects_invalid_identity_links_and_paths
        raise ValueError(result.message)
    return result


def _build_hk_snapshot_result(source_directory: Path, *, version: str) -> dict[str, Any] | Failure:
    """Read five source-owned files and derive one versioned declaration."""
    if not version or not re.fullmatch(r"[A-Za-z0-9_.-]+", version):
        return _rejected("version must be an explicit safe identifier")
    raw = {name: (source_directory / name).read_bytes() for name in _NAMES}
    text = {name: raw[name].decode("utf-8") for name in _NAMES}
    vocabulary = json.loads(text["域.json"])
    if not isinstance(vocabulary, dict) or set(vocabulary) != {
        "域名", "节点类型", "边类型", "问题意识视角", "大纲节", "池", "档"
    }:
        return _rejected("域.json must contain exactly the seven domain fields")
    source_files = {name: {"sha256": sha256(raw[name]).hexdigest(), "bytes": len(raw[name])}
                    for name in _NAMES}
    source_revision = _digest_json(source_files)
    route_rows = _rows(text["来源池.md"], "源线ID")
    query_rows = _rows(text["初始关键词池.md"], "检索式ID")
    if not route_rows or not query_rows:
        return _rejected("source route or query table is empty")
    routes: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    route_queries: dict[str, list[str]] = {row["源线ID"]: [] for row in route_rows}
    if len(route_queries) != len(route_rows):
        return _rejected("duplicate route ID")
    source_registry = _source_registry_result(text["已固化源.md"], set(route_queries))
    if isinstance(source_registry, Failure):
        return source_registry
    seen_queries: set[str] = set()
    for row in query_rows:
        query_id, route_id = row["检索式ID"], row["源线ID"]
        if query_id in seen_queries or route_id not in route_queries:
            return _rejected("duplicate query or unknown source route")
        seen_queries.add(query_id)
        route_queries[route_id].append(query_id)
        queries.append({
            "query_id": query_id, "route_id": route_id, "keyword_group_id": row["词组ID"],
            "expression": row["检索式"], "outline_sections": _multi(row["大纲节"]),
            "perspective": row["问题意识视角"], "target_edge": row["目标边"],
            # The source table's 已执行 status refers to its own prior round.
            # A new preview starts without inheriting that attempt or result.
        })
    for row in route_rows:
        route_id = row["源线ID"]
        leads = _multi(row["候选入口"])
        routes.append({
            "route_id": route_id, "label": row["材料与栏目"], "pool": row["池"],
            "outline_anchor": _headline(row["总纲锚点"]),
            "outline_sections": _multi(row["大纲节"]),
            "perspectives": _multi(row["问题意识视角"]),
            "node_types": _multi(row["拟挂节点类型"]),
            "target_edges": _multi(row["目标边"]),
            "source_leads": leads,
            "source_urls": [lead for lead in leads if lead.startswith(("https://", "http://"))],
            "keyword_group_ids": _multi(row["词组ID"]),
            "priority": row["优先级"],
            "status": "active" if row["状态"] == "在用" else "reserved",
            "query_ids": route_queries[route_id],
        })
    outline = text["分析总纲.md"]
    sections = re.findall(r"^### ([1-4]) (.+)$", outline, flags=re.MULTILINE)
    if [section for section, _ in sections] != vocabulary["大纲节"]:
        return _rejected("outline sections differ from 域.json")
    summary = {
        "title": vocabulary["域名"],
        "sections": [{"section": section, "label": label} for section, label in sections],
        "research_scope": (
            "从水文运动、供水、排水河流、港湾与生活现场调查物质过程、社会关系、阶级意识和文化再生产；"
            "具体关系待材料核实。"
        ),
        "authority": "分析总纲.md 正文是搜集解释的事实源；域.json 是派生运行时词表。",
    }
    return {
        "schema": "mrw.project-retrieval-mode.v1",
        "project_key": "hk_water_investigation",
        "mode_id": "hk-water-investigation-retrieval",
        "version": version,
        "source_revision": source_revision,
        "source_snapshot": {"kind": "checked_in_project_binding", "files": source_files},
        "outline_summary": summary,
        "domain_vocabulary": vocabulary,
        "domain_source_ref": {
            "ref": {"project_key": "hk_water_investigation", "module_id": "retrieval",
                    "namespace": "brief", "type_id": "source", "local_id": "analysis-brief"},
            "observed_revision": source_revision,
            "content_digest": source_files["分析总纲.md"]["sha256"],
        },
        "limits": {"max_queries": 10, "max_materials": 20, "max_followups": 2},
        "routes": routes, "queries": queries, "source_registry": source_registry,
    }


def build_hk_snapshot(source_directory: Path, *, version: str) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=source_owned_five_files+version witness=test:test_build_hk_snapshot_derives_declared_sources",
]:
    """Read five source-owned files and derive one versioned declaration."""
    result = _build_hk_snapshot_result(source_directory, version=version)
    if isinstance(result, Failure):
        # kit:boundary owner=project_retrieval.hk_loader.authoring_import class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_build_hk_snapshot_rejects_invalid_version
        raise ValueError(result.message)
    return result


def write_hk_snapshot(snapshot: dict[str, Any], destination: Path) -> None:
    """Explicitly persist an authored snapshot without overwriting a version."""
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        if previous.get("version") == snapshot.get("version") and previous != snapshot:
            # kit:boundary owner=project_retrieval.hk_loader.versioned_write class=SHELL_BOUNDARY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_version_writer_rejects_identity_replacement
            raise ValueError("changed source requires a new mode version")
        if previous.get("version") != snapshot.get("version"):
            historical = destination.with_name(f"retrieval_mode.v{previous['version']}.json")
            old_bytes = destination.read_bytes()
            if historical.exists():
                if historical.read_bytes() != old_bytes:
                    # kit:boundary owner=project_retrieval.hk_loader.versioned_write class=SHELL_BOUNDARY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_version_writer_rejects_identity_replacement
                    raise ValueError("historical snapshot already exists with different bytes")
            else:
                historical.write_bytes(old_bytes)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
