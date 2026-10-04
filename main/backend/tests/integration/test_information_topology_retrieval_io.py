"""Retrieval source-format mapping and dedicated PostgreSQL round-trip tests."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from functorial_kit import Failure

from app.services.information_topology.contracts import BoundRef, ElementRef, TopologyState
from app.services.information_topology.io.retrieval import (
    build_import_preview, export_retrieval_bundle, export_retrieval_directory,
    resolve_domain_vocabulary,
)
from app.services.information_topology.profiles import validate_state

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.information_topology_retrieval import source_bundle, vocabulary


def test_source_records_map_to_profile_and_export_keeps_order_report_and_extensions(tmp_path):
    source = source_bundle()
    preview = build_import_preview(project_key="it-retrieval", module_id="retrieval",
        namespace="retrieval", source=source, vocabulary=vocabulary(),
        report_body=source["report_body"], report_ref=source["report_ref"])
    assert not isinstance(preview, Failure)
    assert validate_state(preview.profile, preview.state) is None
    assert {element.ref.ref.type_id for element in preview.state.elements} >= {
        "judgment", "clue", "source_route", "keyword_plan", "node:现场", "node:行动者"
    }
    assert next(e for e in preview.state.elements if e.ref.ref.local_id == "query:test:1").attributes["execution_status"] == "not_executed"
    assert next(e for e in preview.state.elements if e.ref.ref.local_id == "attempt:test:1").attributes["result"] == "access_failed"

    edited = tuple(
        type(element)(element.ref, {**element.attributes, "judgment": "DB编辑后的判断"}, element.endpoints)
        if element.ref.ref.local_id == "e:test:1" else element
        for element in preview.state.elements
    )
    exported = export_retrieval_bundle(state=TopologyState(preview.state.profile_id, preview.state.profile_version, edited),
                                       provenance=preview.provenance)
    assert not isinstance(exported, Failure)
    assert exported["source_graph"]["线索"][0]["顺序"] == ["行动者:test", "e:test:1", "行动者:test"]
    assert exported["source_graph"]["边"][0]["判断"] == "DB编辑后的判断"
    assert exported["report_body"] == source["report_body"]
    assert exported["original_files"] == source["original_files"]
    assert exported["mrw-extension.json"]["topology_edits_require_source_owner_apply"] is True
    assert exported["source_graph"]["证据"][0]["名称"] == "测试材料标题"
    output = export_retrieval_directory(tmp_path / "new-export", exported)
    assert (output / "图.json").is_file()
    assert (output / "来源池.md").read_text(encoding="utf-8") == source["original_files"]["来源池.md"]
    with pytest.raises(FileExistsError):
        export_retrieval_directory(output, exported)

    framework_root = Path(os.environ.get("INFORMATION_SEARCH_FRAMEWORK_ROOT",
        "/Users/wangyiliang/Desktop/科学/信息搜索框架"))
    if framework_root.is_dir():
        sys.path.insert(0, str(framework_root))
        try:
            import 信息结构
            errors = 信息结构.validate_graph(exported["source_graph"], domain={
                "域名": "结构测试域", "节点类型": ["现场", "行动者"], "边类型": ["管理"],
                "问题意识视角": ["制度"], "大纲节": ["背景"], "池": ["来源池A"],
                "档": ["A", "B", "C", "D"],
            })
            assert errors == []
        finally:
            sys.path.remove(str(framework_root))

def test_export_retrieval_directory_rejects_invalid_original_paths(tmp_path):
    bundle = {
        "source_graph": {}, "topology": {}, "source_companions": {},
        "mrw-extension.json": {}, "original_files": {"../escape.txt": "blocked"},
    }
    with pytest.raises(ValueError, match="invalid relative source path"):
        export_retrieval_directory(tmp_path / "invalid", bundle)
    colliding = {**bundle, "original_files": {"图.json": "blocked"}}
    with pytest.raises(ValueError, match="collides with generated export file"):
        export_retrieval_directory(tmp_path / "collision", colliding)



def test_import_rejects_changed_domain_source_and_candidate_promotion():
    source = source_bundle()
    other_domain = vocabulary("other-project")
    result = build_import_preview(project_key="it-retrieval", module_id="retrieval",
        namespace="retrieval", source=source, vocabulary=other_domain)
    assert isinstance(result, Failure) and result.code == "SOURCE_CHANGED"

    source["candidates"] = [{"candidate_id": "cand:test:1", "candidate_kind": "judgment",
                              "status": "formal_evidence", "refers_to": ["e:test:1"]}]
    promoted = build_import_preview(project_key="it-retrieval", module_id="retrieval",
        namespace="retrieval", source=source, vocabulary=vocabulary())
    assert isinstance(promoted, Failure) and promoted.code == "INVALID_STRUCTURE"


def test_domain_vocabulary_resolver_uses_explicit_seven_fields_and_bound_source():
    source = source_bundle()
    resolved = resolve_domain_vocabulary("it-retrieval", source)
    assert not isinstance(resolved, Failure)
    assert resolved.name == "结构测试域" and resolved.node_types == ("现场", "行动者")
    assert resolved.source_ref.observed_revision == "brief-r1"
    incomplete = {**source, "domain_vocabulary": {"域名": "缺字段"}}
    failure = resolve_domain_vocabulary("it-retrieval", incomplete)
    assert isinstance(failure, Failure) and failure.code == "INVALID_STRUCTURE"


def test_native_rapid_yes_no_flags_optional_nulls_and_storage_state_identity():
    source = source_bundle()
    source["storage_state_id"] = "run:test:1::clue:test:1"
    source["graph"]["边"][0]["中介状态"] = None
    source["graph"]["线索"][0]["作废"] = "否"
    preview = build_import_preview(project_key="it-retrieval", module_id="retrieval",
        namespace="retrieval", source=source, vocabulary=vocabulary())
    assert not isinstance(preview, Failure)
    assert preview.state_key[-1] == "run:test:1::clue:test:1"
    clue = next(element for element in preview.state.elements if element.ref.ref.type_id == "clue")
    assert clue.attributes["invalidated"] is False
    judgment = next(element for element in preview.state.elements if element.ref.ref.type_id == "judgment")
    assert "mediation_status" not in judgment.attributes
    exported = export_retrieval_bundle(state=preview.state, provenance=preview.provenance)
    assert exported["source_graph"]["线索"][0]["作废"] == "否"
    assert exported["source_graph"]["边"][0]["中介状态"] is None


def test_export_restores_ordered_discontinuities_from_provenance():
    source = source_bundle()
    source["graph"]["线索"][0]["顺序"] = ["行动者:test", "断口:待补来源", "e:test:1", "行动者:test"]
    preview = build_import_preview(project_key="it-retrieval", module_id="retrieval",
        namespace="retrieval", source=source, vocabulary=vocabulary())
    assert not isinstance(preview, Failure)
    exported = export_retrieval_bundle(state=preview.state, provenance=preview.provenance)
    assert exported["source_graph"]["线索"][0]["顺序"] == source["graph"]["线索"][0]["顺序"]


def test_ordered_clue_accepts_material_references():
    source = source_bundle()
    source["materials"] = [{"材料ID": "item:test:1", "标题": "材料", "档": "A",
                             "节点ID": [], "边ID": [], "关系类": [], "快照路径": []}]
    source["graph"]["线索"][0]["顺序"] = ["行动者:test", "item:test:1", "e:test:1"]
    preview = build_import_preview(project_key="it-retrieval", module_id="retrieval",
        namespace="retrieval", source=source, vocabulary=vocabulary())
    assert not isinstance(preview, Failure)
    clue = next(element for element in preview.state.elements if element.ref.ref.type_id == "clue")
    assert [(endpoint.position, endpoint.target.ref.type_id) for endpoint in clue.endpoints] == [
        (0, "node:行动者"), (1, "material"), (2, "judgment")]


def test_missing_material_is_preserved_as_unresolved_without_inventing_source_record():
    source = source_bundle()
    source["graph"]["证据"] = [{"证据ID": "ev:test:1", "边ID": "e:test:1", "材料ID": "item:missing:1",
        "档": "A", "打架": "否", "作用": "支持", "原文定位": "未提供", "原文摘录": "未提供",
        "适用范围": "未提供", "推论说明": "未提供", "证明对象": "事实关系", "来源角色": "直接记录",
        "独立组": "unresolved-fixture"}]
    source["materials"] = []
    source["source_routes"] = [{"route_id": "route:test:1", "pool": "来源池A", "status": "active"}]
    preview = build_import_preview(project_key="it-retrieval", module_id="retrieval",
        namespace="retrieval", source=source, vocabulary=vocabulary())
    assert not isinstance(preview, Failure)
    missing = next(element for element in preview.state.elements if element.ref.ref.local_id == "item:missing:1")
    assert missing.attributes == {"title": "", "url": "", "grade": "",
                                  "reference_status": "unresolved_reference",
                                  "node_ids": [], "edge_ids": [], "relation_classes": [], "snapshot_path": []}
    exported = export_retrieval_bundle(state=preview.state, provenance=preview.provenance)
    assert exported["materials"] == []
    assert exported["source_companions"]["source_routes"] == source["source_routes"]
    assert exported["unresolved_material_refs"] == [{"material_id": "item:missing:1",
        "evidence_ids": ["ev:test:1"], "status": "unresolved_reference"}]


def test_source_digest_changes_when_authoritative_input_changes():
    first = source_bundle()
    second = source_bundle()
    second["graph"]["边"][0]["范围"] = " changed "
    a = build_import_preview(project_key="it-retrieval", module_id="retrieval", namespace="retrieval",
                             source=first, vocabulary=vocabulary())
    b = build_import_preview(project_key="it-retrieval", module_id="retrieval", namespace="retrieval",
                             source=second, vocabulary=vocabulary())
    assert not isinstance(a, Failure) and not isinstance(b, Failure)
    assert a.source_digest != b.source_digest


TEST_URL = os.environ.get("INFORMATION_TOPOLOGY_TEST_DATABASE_URL")
TEST_SCHEMA = os.environ.get("INFORMATION_TOPOLOGY_TEST_SCHEMA")
@pytest.mark.skipif(
    not TEST_URL or not TEST_SCHEMA,
    reason="P07B PostgreSQL round-trip requires P00's dedicated test URL and isolated schema",
)
def test_postgres_import_edit_export_and_source_validator_round_trip():
    """Real P02 repository round-trip; never falls back to an in-memory store."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker

    from app.models.information_topology_entities import InformationTopologyState
    from app.services.information_topology.io.retrieval import RepositoryRetrievalStore, RetrievalStructureIO
    from app.services.information_topology.repository import InformationTopologyRepository, StateWrite
    from app.services.information_topology.profiles import decode_state

    engine = create_engine(TEST_URL, future=True, pool_size=2, max_overflow=0)

    @__import__("sqlalchemy").event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{TEST_SCHEMA}"')
        cursor.close()
        # SQLAlchemy's pool reset rolls back an open transaction on checkout;
        # commit the session-level SET so search_path survives that reset.
        dbapi_connection.commit()

    assert inspect(engine).has_table("information_topology_states", schema=TEST_SCHEMA)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_schema()")).scalar_one() == TEST_SCHEMA
    sessions = sessionmaker(bind=engine, autoflush=False, future=True)
    project_key = f"it-retrieval-{uuid4().hex}"
    source = source_bundle()
    # The test source carries the explicit domain declaration/reference for this unique project.
    source["domain_source_ref"] = {"ref": {"project_key": project_key, "module_id": "retrieval",
        "namespace": "brief", "type_id": "source", "local_id": "analysis-brief"},
        "observed_revision": "brief-r1", "content_digest": "brief-digest"}
    preview = build_import_preview(project_key=project_key, module_id="retrieval", namespace="retrieval",
                                  source=source, vocabulary=vocabulary(project_key), report_body=source["report_body"],
                                  report_ref=source["report_ref"])
    assert not isinstance(preview, Failure)
    profiles = {(preview.profile.profile_id, preview.profile.version): preview.profile}
    repository = InformationTopologyRepository(profiles)
    store = RepositoryRetrievalStore(repository)
    io_port = RetrievalStructureIO(store=store, session_factory=sessions)
    try:
        imported = io_port.import_structure(project_key=project_key, module_id="retrieval", source=source)
        assert imported["accepted"] is True and imported["idempotent"] is False and imported["revision"] == 1
        duplicate = io_port.import_structure(project_key=project_key, module_id="retrieval", source=source)
        assert duplicate["accepted"] is True and duplicate["idempotent"] is True and duplicate["revision"] == 1
        changed_source = {**source, "graph": {**source["graph"], "生成日": "2026-09-25"}}
        changed = io_port.import_structure(project_key=project_key, module_id="retrieval", source=changed_source)
        assert isinstance(changed, Failure) and changed.code == "SOURCE_CHANGED"
        with sessions.begin() as session:
            existing = store.read(session, preview.state_key)
            assert existing["provenance"]["source_digest"] == preview.source_digest
            state = decode_state(preview.profile, existing["payload"])
            changed = tuple(
                type(element)(element.ref, {**element.attributes, "judgment": "DB编辑后的判断"}, element.endpoints)
                if element.ref.ref.local_id == "e:test:1" else element for element in state.elements
            )
            updated = TopologyState(state.profile_id, state.profile_version, changed)
            result = repository.apply_batch(session, states=(StateWrite(
                preview.state_key, updated, existing["revision"], existing["provenance"]),))
            assert result == ({"revision": 2},)
        # A fresh process-like IO instance has no imported/static profile registry.
        restarted_io = RetrievalStructureIO(store=store, session_factory=sessions)
        exported = restarted_io.export_structure(project_key=project_key,
            target={"module_id": "retrieval", "namespace": "retrieval", "state_id": "clue:test:1"},
            format="retrieval-source-bundle.v1")
        assert not isinstance(exported, Failure)
        assert exported["source_graph"]["边"][0]["判断"] == "DB编辑后的判断"
        assert exported["source_graph"]["线索"][0]["顺序"] == source["graph"]["线索"][0]["顺序"]

        # A separate authoritative source edit is rejected before any write.
        with sessions() as session:
            unchanged = store.read(session, preview.state_key)
        assert unchanged["revision"] == 2

        framework_root = Path(os.environ.get("INFORMATION_SEARCH_FRAMEWORK_ROOT",
            "/Users/wangyiliang/Desktop/科学/信息搜索框架"))
        assert framework_root.is_dir(), "P07A framework source root is unavailable"
        sys.path.insert(0, str(framework_root))
        try:
            import 信息结构
            domain = {"域名": "结构测试域", "节点类型": ["现场", "行动者"], "边类型": ["管理"],
                      "问题意识视角": ["制度"], "大纲节": ["背景"], "池": ["来源池A"], "档": ["A", "B", "C", "D"]}
            errors = 信息结构.validate_graph(exported["source_graph"], domain=domain)
            assert errors == []
        finally:
            sys.path.remove(str(framework_root))
    finally:
        engine.dispose()
