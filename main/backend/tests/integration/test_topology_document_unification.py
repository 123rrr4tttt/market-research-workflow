"""Document-owner integration tests on disposable PostgreSQL schemas."""

from __future__ import annotations

from dataclasses import replace
import os
from uuid import uuid4

import pytest
from functorial_kit import Failure
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

from app.models.entities import Document, Source
from app.models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from app.services.information_topology.contracts import topology_failures
from app.services.information_topology.document_materials import (
    bind_material_documents,
    project_document_materials,
    resolve_document,
)
from app.services.information_topology.io.retrieval import (
    RepositoryRetrievalStore,
    RetrievalStructureIO,
    build_import_preview,
)
from app.services.information_topology.modules.retrieval import profile_from_state_payload
from app.services.information_topology.profiles import validate_state
from app.services.information_topology.repository import InformationTopologyRepository, StateWrite
from app.services.information_topology.service import InformationTopologyDependencies, InformationTopologyService
from app.services.ingest.terminal_writer import persist_terminal_document_in_session
from app.settings.config import settings
from fixtures.information_topology_retrieval import source_bundle, vocabulary

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DOCUMENT_UNIFICATION_POSTGRES") != "1",
    reason="requires explicit disposable PostgreSQL schema authorization",
)


@pytest.fixture
def unified():
    engine = create_engine(settings.database_url)
    schema = "test_doc_unification_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        for model in (Source, Document, InformationTopologyState, InformationTopologyLink):
            model.__table__.create(connection)
    sessions = sessionmaker(bind=engine, autoflush=False)

    @event.listens_for(sessions, "after_begin")
    def scope_session(session, transaction, connection):
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))

    repository = InformationTopologyRepository({})
    store = RepositoryRetrievalStore(repository)
    io = RetrievalStructureIO(store=store, session_factory=sessions, material_binder=bind_material_documents)
    service = InformationTopologyService(
        InformationTopologyDependencies(
            profiles={},
            mappings={},
            io=io,
            repository=repository,
            session_factory=sessions,
            material_binder=bind_material_documents,
            read_model_projector=project_document_materials,
            native_resolver=resolve_document,
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


def current_material(service):
    result = service.list_topologies("it-retrieval")
    assert not isinstance(result, Failure)
    return next(e for e in result["items"][0]["topology"]["elements"] if e["ref"]["ref"]["type_id"] == "material")


def test_import_uses_document_owner_and_ordinary_document_apis(unified, monkeypatch):
    sessions, repository, io, service = unified
    source = bundle()
    assert io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)["accepted"]
    assert io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)["idempotent"]
    with sessions() as session:
        document = session.execute(select(Document)).scalar_one()
        doc_id = document.id
        assert document.content is None and document.status == "reference_only"
        row = repository.read_state(session, ("it-retrieval", "retrieval", "retrieval", "clue:test:1"))
        material = next(e for e in row["state"].elements if e.ref.ref.type_id == "material")
        assert row["profile_version"].startswith("2+")
        assert "title" not in material.attributes and "url" not in material.attributes
        assert material.attributes["document_ref"]["local_id"] == str(doc_id)
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
    assert projected["attributes"]["document_id"] == doc_id
    assert projected["attributes"]["title"] == source["materials"][0]["标题"]
    assert service.resolve("it-retrieval", [projected["attributes"]["document_ref"]])["total"] == 1
    from app.api import admin

    monkeypatch.setattr(admin, "SessionLocal", sessions)
    monkeypatch.setattr(admin, "_project_key_from_request", lambda request: "it-retrieval")
    listing = admin.list_documents(None, admin.DocumentListRequest(include_topology_materials=True))["data"]
    assert listing["total"] == 1 and listing["items"][0]["id"] == doc_id
    assert admin.get_document(doc_id)["data"]["uri"] == source["materials"][0]["URL"]
    with sessions.begin() as session:
        result = persist_terminal_document_in_session(
            session,
            {
                "source_name": "collected",
                "doc_type": "news",
                "uri": source["materials"][0]["URL"],
                "content": "actual source body",
                "title": "Collected title",
            },
        )
        assert result["doc_id"] == doc_id and result["updated"] == 1
    assert current_material(service)["attributes"]["title"] == "Collected title"
    assert admin.get_document(doc_id)["data"]["content"] == "actual source body"
    exported = io.export_structure(
        project_key="it-retrieval",
        target={"module_id": "retrieval", "namespace": "retrieval", "state_id": "clue:test:1"},
        format="retrieval-source-bundle.v1",
    )
    assert exported["materials"] == source["materials"]
    assert exported["source_graph"] == source["graph"]
    assert exported["original_files"] == source["original_files"]


def test_migration_reuses_existing_document_preserves_history_and_provenance(unified):
    sessions, repository, io, service = unified
    source = bundle()
    preview = build_import_preview(
        project_key="it-retrieval", module_id="retrieval", namespace="retrieval", source=source, vocabulary=vocabulary()
    )
    with sessions.begin() as session:
        document = Document(
            doc_type="news", title="Owner title", content="Owner body", uri=source["materials"][0]["URL"]
        )
        session.add(document)
        session.flush()
        doc_id = document.id
        assert not isinstance(
            repository.apply_batch(
                session, states=(StateWrite(preview.state_key, preview.state, None, preview.provenance),)
            ),
            Failure,
        )
    assert service.merge_material_documents("it-retrieval")["migrated_states"] == 1
    assert service.merge_material_documents("it-retrieval")["migrated_states"] == 0
    with sessions() as session:
        assert session.execute(select(func.count(Document.id))).scalar_one() == 1
        current = repository.read_state(session, preview.state_key)
        historical = repository.read_state(session, preview.state_key, revision=1)
        assert current["provenance"] == preview.provenance
        assert historical["state"] == preview.state
        assert current["revision"] == 2
    assert current_material(service)["attributes"]["document_id"] == doc_id
    assert current_material(service)["attributes"]["title"] == "Owner title"


def test_unresolved_material_does_not_create_a_document(unified):
    sessions, repository, io, service = unified
    source = bundle()
    source["materials"] = []
    assert io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)["accepted"]
    with sessions() as session:
        assert session.execute(select(func.count(Document.id))).scalar_one() == 0
    material = current_material(service)
    assert material["attributes"]["reference_status"] == "unresolved_reference"
    assert "document_ref" not in material["attributes"]


def test_document_writes_rollback_when_topology_write_fails(unified):
    sessions, repository, io, service = unified

    class RejectingStore(RepositoryRetrievalStore):
        def write(self, session, preview, *, expected_revision):
            return topology_failures.fail("VERSION_CONFLICT", "injected topology conflict")

    rejecting = RetrievalStructureIO(
        store=RejectingStore(repository), session_factory=sessions, material_binder=bind_material_documents
    )
    result = rejecting.import_structure(project_key="it-retrieval", module_id="retrieval", source=bundle())
    assert isinstance(result, Failure) and result.code == "VERSION_CONFLICT"
    with sessions() as session:
        assert session.execute(select(func.count(Document.id))).scalar_one() == 0
        assert session.execute(select(func.count(Source.id))).scalar_one() == 0
        assert repository.list_current_states(session, "it-retrieval") == ()
