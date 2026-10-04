from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from functorial_kit import Failure

from app.api.information_topology import router
from app.services.information_topology.modules.method import method_profile
from app.services.information_topology.modules.report import report_profile
from app.services.information_topology.service import (
    InformationTopologyDependencies,
    InformationTopologyService,
)
from app.services.information_topology.io.retrieval import RetrievalStructureIO
from app.services.information_topology.contracts import BoundRef, Element, ElementRef, TopologyState, topology_failures
from app.services.information_topology.profiles import ProfileSpec, TypeRule, encode_state
from app.services.information_topology.repository import LinkRead, StateRead, StateWrite
from app.services.projects.context import bind_project

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.information_topology_retrieval import source_bundle


class _NoStructureIO:
    def import_structure(self, *, project_key, module_id, source):
        return {"module_id": module_id, "accepted": True}

    def export_structure(self, *, project_key, target, format):
        return {"format": format, "content": {"kind": "test"}}


def _client(service=None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.information_topology_service = service or InformationTopologyService(
        InformationTopologyDependencies(
            profiles={(p.profile_id, p.version): p for p in (report_profile, method_profile)},
            mappings={}, io=_NoStructureIO(), session_factory=_FakeSession,
        )
    )

    @app.middleware("http")
    async def _bind_test_project(request, call_next):
        with bind_project(request.headers.get("X-Project-Key", "topology_api_test")):
            return await call_next(request)

    return TestClient(app)


def test_information_topology_routes_and_profiles_use_api_envelope():
    client = _client()
    response = client.get("/api/v1/information-topology/profiles", headers={"X-Project-Key": "topology_api_test"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["error"] is None
    assert {item["profile_id"] for item in payload["data"]["items"]} == {
        "information_topology.report_outline", "information_topology.method_description"
    }
    topologies = client.get("/api/v1/information-topology/topologies", headers={"X-Project-Key": "topology_api_test"})
    assert topologies.status_code == 200
    assert topologies.json()["data"] == {"items": [], "total": 0}


def test_resolve_rejects_nested_cross_project_reference_with_non_200_envelope():
    client = _client()
    body = {"refs": [{
        "project_key": "other_project", "module_id": "report", "namespace": "outline",
        "type_id": "section", "local_id": "section-1",
    }]}
    response = client.post("/api/v1/information-topology/resolve", json=body,
                           headers={"X-Project-Key": "topology_api_test"})
    assert response.status_code == 404
    error = response.json()["detail"]
    assert error["status"] == "error"
    assert error["error"]["code"] == "UNRESOLVABLE_REFERENCE"


def test_invalid_operation_shape_is_rejected():
    client = _client()
    response = client.post("/api/v1/information-topology/relations/find", json={"ref": {}},
                           headers={"X-Project-Key": "topology_api_test"})
    assert response.status_code == 422


def test_import_export_are_injected_and_keep_explicit_result_keys():
    client = _client()
    headers = {"X-Project-Key": "topology_api_test"}
    imported = client.post("/api/v1/information-topology/imports", headers=headers,
                           json={"module_id": "retrieval", "source": {"kind": "fixture"}})
    exported = client.post("/api/v1/information-topology/exports", headers=headers,
                           json={"target": {"module_id": "report", "namespace": "outline",
                                             "state_id": "report", "revision": 1},
                                 "format": "native.v1"})
    assert imported.status_code == 200
    assert imported.json()["data"]["import_result"]["accepted"] is True
    assert exported.status_code == 200
    assert exported.json()["data"]["export_result"]["format"] == "native.v1"


def test_retrieval_import_api_resolves_project_semantics_before_topology_write():
    class _ImportSession:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        @contextmanager
        def begin(self):
            yield self

    class _CaptureTopologyStore:
        def __init__(self):
            self.preview = None

        def read(self, _session, _key):
            return None

        def write(self, _session, preview, *, expected_revision):
            assert expected_revision is None
            self.preview = preview
            return ({"revision": 1},)

    store = _CaptureTopologyStore()
    io_port = RetrievalStructureIO(store=store, session_factory=_ImportSession)
    service = InformationTopologyService(InformationTopologyDependencies(
        profiles={(p.profile_id, p.version): p for p in (report_profile, method_profile)},
        mappings={}, io=io_port, session_factory=_FakeSession,
    ))
    source = source_bundle()
    source["domain_source_ref"]["ref"]["project_key"] = "it_retrieval"
    response = _client(service).post(
        "/api/v1/information-topology/imports",
        headers={"X-Project-Key": "it_retrieval"},
        json={"module_id": "retrieval", "source": source},
    )

    assert response.status_code == 200, response.text
    result = response.json()["data"]["import_result"]
    assert result["accepted"] is True and result["revision"] == 1
    assert store.preview is not None
    assert store.preview.profile.profile_id == store.preview.state.profile_id
    assert any(element.ref.ref.type_id == "domain_vocabulary" for element in store.preview.state.elements)
    evidence = next(element for element in store.preview.state.elements
                    if element.ref.ref.type_id == "evidence")
    assert evidence.attributes["name"] == "测试材料标题"
    clue = next(element for element in store.preview.state.elements
                if element.ref.ref.type_id == "clue")
    assert clue.attributes["name"] == "线索链：测试现场"
    material = next(element for element in store.preview.state.elements
                    if element.ref.ref.type_id == "material")
    assert "name" not in material.attributes
    assert material.attributes["title"] == "测试材料标题"


def test_topology_operation_paths_are_exposed():
    paths = set(_client().get("/openapi.json").json()["paths"])
    assert {
        "/api/v1/information-topology/profiles",
        "/api/v1/information-topology/topologies",
        "/api/v1/information-topology/resolve",
        "/api/v1/information-topology/topologies/read",
        "/api/v1/information-topology/relations/find",
        "/api/v1/information-topology/mappings/preview",
        "/api/v1/information-topology/patches",
        "/api/v1/information-topology/imports",
        "/api/v1/information-topology/exports",
    } <= paths


class _FakeSession:
    @contextmanager
    def begin(self):
        yield self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, _statement):
        class _Scalars:
            @staticmethod
            def all():
                return []

        class _Result:
            @staticmethod
            def all():
                return []

            @staticmethod
            def scalars():
                return _Scalars()

        return _Result()


class _AtomicFakeRepository:
    """Test double for repository transaction semantics; production uses PostgreSQL."""

    def __init__(self, profile):
        self.profile = profile
        self.states = {}
        self.links = {}
        self.before_apply = None

    def seed_state(self, key, revision=1):
        state = _state(key[0], key[1], key[2], key[3], str(revision))
        self.states[key] = {"key": key, "revision": revision, "profile_id": state.profile_id,
                            "profile_version": state.profile_version,
                            "payload": dict(encode_state(self.profile, state)), "deleted": False,
                            "digest": "test-digest"}

    def read_state(self, _session, key, *, revision=None):
        row = self.states.get(key)
        if row is None or (revision is not None and row["revision"] != revision):
            return None
        return dict(row)

    def apply_batch(self, _session, *, states=(), links=(), read_set=(), link_read_set=()):
        if self.before_apply:
            self.before_apply()
            self.before_apply = None
        state_expectations = {entry.key: entry.expected_revision for entry in read_set}
        state_expectations.update({entry.key: entry.expected_revision for entry in states})
        for key, expected in state_expectations.items():
            actual = self.states.get(key, {}).get("revision")
            if actual != expected:
                return topology_failures.fail("VERSION_CONFLICT", "state base revision changed")
        link_expectations = {(entry.project_key, entry.link_id): entry.expected_revision for entry in link_read_set}
        for write in links:
            link_expectations[(write.project_key, write.link_id)] = write.expected_revision
        for key, expected in link_expectations.items():
            actual = self.links.get(key, {}).get("revision")
            if actual != expected:
                return topology_failures.fail("VERSION_CONFLICT", "link base revision changed")
        result = []
        for write in states:
            old = self.states.get(write.key)
            revision = 1 if old is None else old["revision"] + 1
            self.states[write.key] = {"key": write.key, "revision": revision,
                                      "profile_id": write.state.profile_id,
                                      "profile_version": write.state.profile_version,
                                      "payload": dict(encode_state(self.profile, write.state)), "deleted": False,
                                      "digest": "test-digest"}
            result.append({"revision": revision})
        for write in links:
            key = (write.project_key, write.link_id)
            revision = 1 if key not in self.links else self.links[key]["revision"] + 1
            self.links[key] = {"revision": revision}
            result.append({"revision": revision})
        return tuple(result)


def _state(project, module, namespace, state_id, observed_revision):
    return TopologyState("batch.test", "1", (
        Element(BoundRef(ElementRef(project, module, namespace, "node", state_id), observed_revision)),
    ))


def _batch_service():
    profile = ProfileSpec("batch.test", "1", {"node": TypeRule()}, frozenset())
    repository = _AtomicFakeRepository(profile)
    repository.seed_state(("topology_api_test", "m", "n", "s1"))
    repository.seed_state(("topology_api_test", "m", "n", "s2"))
    service = InformationTopologyService(InformationTopologyDependencies(
        profiles={(profile.profile_id, profile.version): profile}, mappings={}, io=_NoStructureIO(),
        repository=repository, session_factory=_FakeSession,
    ))
    return service, repository


def _replace_state(state_id):
    old = BoundRef(ElementRef("topology_api_test", "m", "n", "node", state_id), "1")
    new = Element(BoundRef(old.ref, "2"))
    return {"target": {"module_id": "m", "namespace": "n", "state_id": state_id},
            "base_revision": 1,
            "patch": [{"action": "replace", "ref": {
                "ref": {"project_key": old.ref.project_key, "module_id": old.ref.module_id,
                        "namespace": old.ref.namespace, "type_id": old.ref.type_id,
                        "local_id": old.ref.local_id}, "observed_revision": old.observed_revision,
                "content_digest": None},
                "element": {"ref": {"ref": {"project_key": new.ref.ref.project_key,
                                                "module_id": new.ref.ref.module_id,
                                                "namespace": new.ref.ref.namespace,
                                                "type_id": new.ref.ref.type_id,
                                                "local_id": new.ref.ref.local_id},
                                    "observed_revision": new.ref.observed_revision,
                                    "content_digest": None}, "attributes": {}, "endpoints": []}}]}


def test_batch_second_state_conflict_leaves_all_targets_unchanged():
    service, repository = _batch_service()
    key_second = ("topology_api_test", "m", "n", "s2")

    def concurrent_change():
        repository.states[key_second]["revision"] = 2

    repository.before_apply = concurrent_change
    result = service.apply_batch("topology_api_test", state_patches=[_replace_state("s1"), _replace_state("s2")],
                                 link_writes=[], read_set=[], link_read_set=[])
    assert isinstance(result, Failure) and result.code == "VERSION_CONFLICT"
    assert repository.states[("topology_api_test", "m", "n", "s1")]["revision"] == 1
    assert repository.states[key_second]["revision"] == 2


def test_link_read_set_conflict_leaves_state_and_link_unchanged():
    service, repository = _batch_service()
    repository.links[("topology_api_test", "guard-link")] = {"revision": 2}
    result = service.apply_batch(
        "topology_api_test", state_patches=[_replace_state("s1")], link_writes=[], read_set=[],
        link_read_set=[{"link_id": "guard-link", "base_revision": 1}],
    )
    assert isinstance(result, Failure) and result.code == "VERSION_CONFLICT"
    assert repository.states[("topology_api_test", "m", "n", "s1")]["revision"] == 1
    assert repository.links[("topology_api_test", "guard-link")]["revision"] == 2


def test_patch_link_nested_ref_cannot_cross_project():
    client = _client()
    response = client.post("/api/v1/information-topology/patches",
                           headers={"X-Project-Key": "topology_api_test"}, json={
        "link_writes": [{"link_id": "cross", "record_kind": "relation", "type_or_rule_ref": "rel",
                         "endpoints": [{"role": "target", "target": {"ref": {
                             "project_key": "another_project", "module_id": "m", "namespace": "n",
                             "type_id": "node", "local_id": "x"}, "observed_revision": "1"}}]}]
    })
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "UNRESOLVABLE_REFERENCE"


def test_patch_api_accepts_explicit_multi_target_batch_shape():
    service, _repository = _batch_service()
    client = _client(service)
    response = client.post("/api/v1/information-topology/patches",
                           headers={"X-Project-Key": "topology_api_test"}, json={
        "state_patches": [_replace_state("s1")],
        "link_writes": [{"link_id": "relation-1", "record_kind": "relation",
                         "type_or_rule_ref": "relates", "endpoints": [
                             {"role": "source", "target": {"ref": {
                                 "project_key": "topology_api_test", "module_id": "m", "namespace": "n",
                                 "type_id": "node", "local_id": "s1"}, "observed_revision": "2"}},
                             {"role": "target", "target": {"ref": {
                                 "project_key": "topology_api_test", "module_id": "m", "namespace": "n",
                                 "type_id": "node", "local_id": "s2"}, "observed_revision": "1"}},
                         ]}],
        "link_read_set": [],
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state_revisions"][0]["revision"] == 2
    assert data["link_revisions"] == [{"link_id": "relation-1", "revision": 1}]


def test_patch_api_explicitly_creates_initial_state_and_link_together():
    service, repository = _batch_service()
    client = _client(service)
    initial_state = _state("topology_api_test", "graph", "view", "g1", "1")
    response = client.post("/api/v1/information-topology/patches",
                           headers={"X-Project-Key": "topology_api_test"}, json={
        "state_patches": [{
            "target": {"module_id": "graph", "namespace": "view", "state_id": "g1"},
            "base_revision": None,
            "initial_state": {
                "profile_id": initial_state.profile_id,
                "profile_version": initial_state.profile_version,
                "elements": [{
                    "ref": {"ref": {"project_key": "topology_api_test", "module_id": "graph",
                                    "namespace": "view", "type_id": "node", "local_id": "g1"},
                            "observed_revision": "1", "content_digest": None},
                    "attributes": {}, "endpoints": [],
                }],
            },
        }],
        "link_writes": [{"link_id": "graph-relation", "record_kind": "relation",
                         "type_or_rule_ref": "contains", "endpoints": [
                             {"role": "source", "target": {"ref": {
                                 "project_key": "topology_api_test", "module_id": "graph_view",
                                 "namespace": "view", "type_id": "graph_node", "local_id": "g1"},
                                 "observed_revision": "1"}},
                             {"role": "target", "target": {"ref": {
                                 "project_key": "topology_api_test", "module_id": "graph_view",
                                 "namespace": "view", "type_id": "graph_node", "local_id": "g2"},
                                 "observed_revision": "1"}},
                         ]}],
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state_revisions"][0]["revision"] == 1
    assert data["link_revisions"] == [{"link_id": "graph-relation", "revision": 1}]
    assert repository.states[("topology_api_test", "graph", "view", "g1")]["revision"] == 1
