"""Material-owner integration tests on disposable PostgreSQL schemas."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import os
from uuid import uuid4

import pytest
from functorial_kit import Failure
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

from app.models.entities import Material, Source
from app.services.document_queries.identity import material_identity, canonical_material_identity
from app.models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from app.services.information_topology.contracts import topology_failures
from app.services.information_topology.document_materials import (
    MaterialBinder,
    bind_materials,
    project_materials,
    resolve_material,
)
from app.services.information_topology.io.retrieval import (
    _digest,
    _source_ref_wire,
    _state_digest,
    RepositoryRetrievalStore,
    RetrievalStructureIO,
    build_import_preview,
)
from app.services.information_topology.modules.retrieval import (
    _make_legacy_document_retrieval_profile,
    _make_legacy_retrieval_profile,
    profile_from_state_payload,
)
from app.services.information_topology.profiles import validate_state
from app.services.information_topology.repository import InformationTopologyRepository, StateWrite
from app.services.information_topology.service import InformationTopologyDependencies, InformationTopologyService
from app.services.ingest.terminal_writer import persist_terminal_material_in_session
from fixtures.information_topology_retrieval import source_bundle, vocabulary

DSN = "postgresql+psycopg2://postgres@127.0.0.1:50931/material_migration_test"
DSN_ENV = "MATERIAL_MIGRATION_TEST_DATABASE_URL"

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MATERIAL_UNIFICATION_POSTGRES") != "1"
    or os.environ.get(DSN_ENV, "").strip() != DSN,
    reason="requires the exclusive disposable Material PostgreSQL test DSN",
)


@pytest.fixture
def unified():
    engine = create_engine(DSN)
    schema = "test_material_unification_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        for model in (Source, Material, InformationTopologyState, InformationTopologyLink):
            model.__table__.create(connection)
    sessions = sessionmaker(bind=engine, autoflush=False)

    @event.listens_for(sessions, "after_begin")
    def scope_session(session, transaction, connection):
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))

    repository = InformationTopologyRepository({})
    store = RepositoryRetrievalStore(repository)
    io = RetrievalStructureIO(store=store, session_factory=sessions, material_binder=bind_materials)
    service = InformationTopologyService(
        InformationTopologyDependencies(
            profiles={},
            mappings={},
            io=io,
            repository=repository,
            session_factory=sessions,
            material_binder=bind_materials,
            read_model_projector=project_materials,
            native_resolver=resolve_material,
        )
    )
    try:
        yield sessions, repository, io, service
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def bundle():
    source = source_bundle()
    source["materials"][0]["URL"] = "https://example.test/document"
    return source


def seed_current_material(sessions, source, *, title=None, content=None):
    raw = source["materials"][0]
    with sessions.begin() as session:
        material = Material(
            material_type="news",
            title=title if title is not None else raw["标题"],
            content=content,
            status="reference_only" if content is None else "available",
            uri=raw["URL"],
            extracted_data={"project_key": "it-retrieval"},
        )
        session.add(material)
        session.flush()
        material_id = int(material.id)
    raw["material_ref"] = material_identity("it-retrieval", material_id)
    return material_id


def legacy_preview(source, *, profile_version, document_ids=None):
    declared_vocabulary = vocabulary()
    current_source = deepcopy(source)
    for position, material in enumerate(current_source["materials"], start=1):
        material["material_id"] = (
            document_ids[material["材料ID"]] if document_ids is not None else position
        )
    preview = build_import_preview(
        project_key="it-retrieval",
        module_id="retrieval",
        namespace="retrieval",
        source=current_source,
        vocabulary=declared_vocabulary,
    )
    assert not isinstance(preview, Failure)
    profile = (
        _make_legacy_document_retrieval_profile(declared_vocabulary)
        if profile_version == "2+"
        else _make_legacy_retrieval_profile(declared_vocabulary)
    )
    materials_by_id = {material["材料ID"]: material for material in source["materials"]}
    elements = []
    for element in preview.state.elements:
        if element.ref.ref.type_id == "domain_vocabulary":
            element = replace(element, ref=replace(element.ref, observed_revision=profile.version))
        elif element.ref.ref.type_id == "material":
            raw = materials_by_id[element.ref.ref.local_id]
            attributes = dict(element.attributes)
            attributes.pop("material_ref", None)
            attributes.pop("placement_title", None)
            if document_ids is not None:
                document_id = document_ids[element.ref.ref.local_id]
                attributes["document_ref"] = {
                    "project_key": "it-retrieval",
                    "module_id": "documents",
                    "namespace": "documents",
                    "type_id": "document",
                    "local_id": str(document_id),
                }
                attributes["snapshot_path"] = [f"document:{document_id}"]
            else:
                attributes["title"] = raw["标题"]
                if raw.get("URL"):
                    attributes["url"] = raw["URL"]
            element = replace(element, attributes=attributes)
        elements.append(element)
    state = replace(preview.state, profile_version=profile.version, elements=tuple(elements))
    assert state.profile_version.startswith(profile_version)
    assert validate_state(profile, state) is None
    source_digest = _digest({"source": source, "vocabulary": _source_ref_wire(declared_vocabulary)})
    return replace(
        preview,
        state=state,
        profile=profile,
        source_digest=source_digest,
        provenance={
            **preview.provenance,
            "source_digest": source_digest,
            "initial_state_digest": _state_digest(state),
        },
    )


def current_material(service):
    result = service.list_topologies("it-retrieval")
    assert not isinstance(result, Failure)
    return next(e for e in result["items"][0]["topology"]["elements"] if e["ref"]["ref"]["type_id"] == "material")


def test_import_uses_material_owner_and_ordinary_material_apis(unified, monkeypatch):
    sessions, repository, io, service = unified
    source = bundle()
    material_id = seed_current_material(sessions, source)
    assert io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)["accepted"]
    assert io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)["idempotent"]
    with sessions() as session:
        material_row = session.execute(select(Material)).scalar_one()
        assert material_row.id == material_id
        assert material_row.content is None and material_row.status == "reference_only"
        row = repository.read_state(session, ("it-retrieval", "retrieval", "retrieval", "clue:test:1"))
        material = next(e for e in row["state"].elements if e.ref.ref.type_id == "material")
        assert row["profile_version"].startswith("3+")
        assert "title" not in material.attributes and "url" not in material.attributes
        assert material.attributes["material_ref"] == material_identity("it-retrieval", material_id)
        assert "document_ref" not in material.attributes
        forged = replace(material, attributes={**material.attributes, "title": "second owner"})
        profile = profile_from_state_payload("it-retrieval", row["profile_id"], row["profile_version"], row["payload"])
        assert isinstance(
            validate_state(
                profile,
                replace(row["state"], elements=tuple(forged if e == material else e for e in row["state"].elements)),
            ),
            Failure,
        )
    projected = current_material(service)
    assert projected["attributes"]["material_ref"] == material_identity("it-retrieval", material_id)
    assert projected["attributes"]["title"] == source["materials"][0]["标题"]
    assert service.resolve("it-retrieval", [projected["attributes"]["material_ref"]])["total"] == 1
    assert isinstance(
        service.resolve(
            "it-retrieval",
            [
                {
                    "project_key": "it-retrieval",
                    "module_id": "documents",
                    "namespace": "documents",
                    "type_id": "document",
                    "local_id": str(material_id),
                }
            ],
        ),
        Failure,
    )
    assert isinstance(service.resolve("it-retrieval", [material_identity("other", material_id)]), Failure)
    from app.api import admin
    from app.services import document_admin

    monkeypatch.setattr(document_admin, "SessionLocal", sessions)
    monkeypatch.setattr(admin, "_project_key_from_request", lambda request: "it-retrieval")
    listing = admin.list_materials(None, admin.MaterialListRequest())["data"]
    assert listing["total"] == 1 and listing["items"][0]["material_id"] == material_id
    assert admin.get_material(material_id)["data"]["uri"] == source["materials"][0]["URL"]
    with sessions.begin() as session:
        result = persist_terminal_material_in_session(
            session,
            {
                "source_name": "collected",
                "material_type": "news",
                "uri": source["materials"][0]["URL"],
                "content": "actual source body",
                "title": "Collected title",
            },
        )
        assert result["material_id"] == material_id and result["updated"] == 1
    assert current_material(service)["attributes"]["title"] == "Collected title"
    assert admin.get_material(material_id)["data"]["content"] == "actual source body"
    exported = io.export_structure(
        project_key="it-retrieval",
        target={"module_id": "retrieval", "namespace": "retrieval", "state_id": "clue:test:1"},
        format="retrieval-source-bundle.v1",
    )
    assert exported["materials"] == source["materials"]
    assert exported["source_graph"] == source["graph"]
    assert exported["original_files"] == source["original_files"]


def test_migration_reuses_existing_material_preserves_history_and_provenance(unified):
    sessions, repository, io, service = unified
    source = bundle()
    preview = legacy_preview(source, profile_version="1+")
    with sessions.begin() as session:
        material_row = Material(
            material_type="news", title="Owner title", content="Owner body", uri=source["materials"][0]["URL"]
        )
        session.add(material_row)
        session.flush()
        material_id = material_row.id
        assert not isinstance(
            repository.apply_batch(
                session, states=(StateWrite(preview.state_key, preview.state, None, preview.provenance),)
            ),
            Failure,
        )
    assert service.merge_materials("it-retrieval")["migrated_states"] == 1
    assert service.merge_materials("it-retrieval")["migrated_states"] == 0
    with sessions() as session:
        assert session.execute(select(func.count(Material.id))).scalar_one() == 1
        current = repository.read_state(session, preview.state_key)
        historical = repository.read_state(session, preview.state_key, revision=1)
        assert current["provenance"] == preview.provenance
        assert historical["state"] == preview.state
        assert current["revision"] == 2
    assert current_material(service)["attributes"]["material_ref"] == material_identity("it-retrieval", material_id)
    assert current_material(service)["attributes"]["title"] == "Owner title"


def test_unresolved_material_does_not_create_a_material(unified):
    sessions, repository, io, service = unified
    source = bundle()
    source["materials"] = []
    assert io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)["accepted"]
    with sessions() as session:
        assert session.execute(select(func.count(Material.id))).scalar_one() == 0
    material = current_material(service)
    assert material["attributes"]["reference_status"] == "unresolved_reference"
    assert "document_ref" not in material["attributes"]
    assert "material_ref" not in material["attributes"]


def test_v2_legacy_address_transports_once_without_changing_endpoints_or_history(unified):
    sessions, repository, io, service = unified
    source = bundle()
    with sessions.begin() as session:
        material = Material(
            material_type="news",
            title="Owner title",
            content="Owner body",
            status="available",
            uri=source["materials"][0]["URL"],
            extracted_data={"project_key": "it-retrieval"},
        )
        session.add(material)
        session.flush()
        material_id = int(material.id)
    preview = legacy_preview(
        source,
        profile_version="2+",
        document_ids={source["materials"][0]["材料ID"]: material_id},
    )
    historical = preview.state
    with sessions.begin() as session:
        assert not isinstance(repository.apply_batch(
            session, states=(StateWrite(preview.state_key, historical, None, preview.provenance),)
        ), Failure)
    assert service.merge_materials("it-retrieval")["migrated_states"] == 1
    assert service.merge_materials("it-retrieval")["migrated_states"] == 0
    with sessions() as session:
        migrated = repository.read_state(session, preview.state_key)
        old = repository.read_state(session, preview.state_key, revision=1)
        assert old["state"] == historical
        assert migrated["profile_version"].startswith("3+")
        assert [e.ref for e in migrated["state"].elements] == [e.ref for e in historical.elements]
        assert [e.endpoints for e in migrated["state"].elements] == [e.endpoints for e in historical.elements]
        assert session.execute(select(func.count(Material.id))).scalar_one() == 1
        material = next(e for e in migrated["state"].elements if e.ref.ref.type_id == "material")
        assert "document_ref" not in material.attributes
        assert "snapshot_path" not in material.attributes
        assert canonical_material_identity("other", material.attributes["material_ref"]) is None


def test_current_binder_rejects_legacy_body_aliases_without_rebinding_material(unified):
    sessions, repository, io, service = unified
    source = bundle()
    seed_current_material(sessions, source)
    assert io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)["accepted"]
    with sessions.begin() as session:
        row = repository.list_current_states(session, "it-retrieval")[0]
        state = repository.read_state(
            session,
            ("it-retrieval", row["module_id"], row["namespace"], row["state_id"]),
        )["state"]
        material = next(e for e in state.elements if e.ref.ref.type_id == "material")
        conflict = replace(
            material,
            attributes={
                **material.attributes,
                "document_ref": {
                    "project_key": "it-retrieval",
                    "module_id": "documents",
                    "namespace": "documents",
                    "type_id": "document",
                    "local_id": str(int(material.attributes["material_ref"]["local_id"]) + 1),
                },
            },
        )
        invalid_current = replace(
            state,
            elements=tuple(conflict if e == material else e for e in state.elements),
        )
        result = MaterialBinder().bind(session, invalid_current)
        assert isinstance(result, Failure) and result.code == "INVALID_STRUCTURE"
        assert session.execute(select(func.count(Material.id))).scalar_one() == 1


def test_material_writes_rollback_when_topology_write_fails(unified):
    sessions, repository, io, service = unified
    source = bundle()
    material_id = seed_current_material(sessions, source)

    class RejectingStore(RepositoryRetrievalStore):
        def write(self, session, preview, *, expected_revision):
            return topology_failures.fail("VERSION_CONFLICT", "injected topology conflict")

    rejecting = RetrievalStructureIO(
        store=RejectingStore(repository), session_factory=sessions, material_binder=bind_materials
    )
    result = rejecting.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)
    assert isinstance(result, Failure) and result.code == "VERSION_CONFLICT"
    with sessions() as session:
        assert session.execute(select(Material.id)).scalar_one() == material_id
        assert session.execute(select(func.count(Source.id))).scalar_one() == 0
        assert repository.list_current_states(session, "it-retrieval") == ()
