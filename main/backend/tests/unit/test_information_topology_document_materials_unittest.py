from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.services.document_queries.identity import material_identity
from app.services.information_topology.contracts import (
    BoundRef,
    Element,
    ElementRef,
    TopologyState,
    topology_failures,
)
from app.services.information_topology.document_materials import (
    MaterialBinder,
    migrate_legacy_material_states,
    project_materials,
    read_material,
)
from app.services.information_topology.io.retrieval import RetrievalStructureIO, build_import_preview
from app.services.information_topology.service import InformationTopologyService
from functorial_kit import Failure
from sqlalchemy.orm import Session

pytestmark = pytest.mark.unit


def _session_returning(document: object) -> Session:
    session = MagicMock(spec=Session)
    session.execute.return_value.scalar_one_or_none.return_value = document
    return session


def test_read_material_accepts_only_the_exact_canonical_material_address() -> None:
    material = SimpleNamespace(id=42, extracted_data={"project_key": "demo"})
    session = _session_returning(material)

    assert read_material(session, "demo", material_identity("demo", 42)) is material
    assert read_material(
        session,
        "demo",
        {
            "project_key": "demo",
            "module_id": "documents",
            "namespace": "documents",
            "type_id": "document",
            "local_id": "42",
        },
    ) is None
    assert read_material(session, "demo", {**material_identity("demo", 42), "extra": "forged"}) is None
    assert session.execute.call_count == 1


def test_project_materials_hydrates_only_the_derived_read_model() -> None:
    material = SimpleNamespace(
        id=42,
        title="Canonical material",
        uri="https://example.test/material/42",
        summary="Evidence summary",
        status="active",
        updated_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        text_hash=None,
        extracted_data={"project_key": "demo"},
    )
    session = _session_returning(material)
    wire = {
        "kind": "information_topology.state.v1",
        "elements": [
            {
                "ref": {
                    "ref": {
                        "project_key": "demo",
                        "module_id": "materials",
                        "namespace": "materials",
                        "type_id": "material",
                        "local_id": "placement-1",
                    },
                    "observed_revision": "r1",
                },
                "attributes": {"material_ref": material_identity("demo", 42)},
                "endpoints": [],
            }
        ],
    }

    projected = project_materials(session, "demo", wire)
    attrs = projected["elements"][0]["attributes"]

    assert attrs["material_ref"] == material_identity("demo", 42)
    assert "material_id" not in attrs
    assert attrs["title"] == "Canonical material"
    assert attrs["material_revision"] == "2026-10-06T00:00:00+00:00"
    assert wire["elements"][0]["attributes"] == {"material_ref": material_identity("demo", 42)}


def test_current_import_preview_builds_v3_and_binds_only_explicit_material_identity() -> None:
    from main.backend.tests.integration.fixtures.information_topology_retrieval import (
        source_bundle,
        vocabulary,
    )

    source = source_bundle()
    rejected = build_import_preview(
        project_key="it-retrieval",
        module_id="retrieval",
        namespace="retrieval",
        source=source,
        vocabulary=vocabulary(),
    )
    assert isinstance(rejected, Failure) and rejected.code == "INVALID_STRUCTURE"
    source["materials"][0]["material_id"] = 42
    preview = build_import_preview(
        project_key="it-retrieval",
        module_id="retrieval",
        namespace="retrieval",
        source=source,
        vocabulary=vocabulary(),
    )

    assert not isinstance(preview, Failure)
    assert preview.state.profile_version.startswith("3+")
    placement = next(
        element for element in preview.state.elements if element.ref.ref.type_id == "material"
    )
    assert placement.attributes["material_ref"] == material_identity("it-retrieval", 42)
    assert "title" not in placement.attributes
    assert "url" not in placement.attributes
    material = SimpleNamespace(id=42, extracted_data={"project_key": "it-retrieval"})
    session = _session_returning(material)
    session.__enter__.return_value = session
    transaction = MagicMock()
    transaction.__enter__.return_value = None
    transaction.__exit__.return_value = False
    session.begin.return_value = transaction
    bound_states: list[TopologyState] = []

    class Store:
        def read(self, _session, _key):
            return None

        def write(self, _session, imported, *, expected_revision):
            assert expected_revision is None
            return ({"revision": 1},)

    def bind_current(_session, state):
        bound = MaterialBinder().bind(_session, state)
        if not isinstance(bound, Failure):
            bound_states.append(bound)
        return bound

    io = RetrievalStructureIO(
        store=Store(),
        session_factory=lambda: session,
        material_binder=bind_current,
    )
    imported = io.import_structure(project_key="it-retrieval", module_id="retrieval", source=source)

    assert imported["accepted"] is True
    assert len(bound_states) == 1 and bound_states[0].profile_version.startswith("3+")


def _legacy_state(*, namespace: str, title: str, locator: str, edge_id: str) -> TopologyState:
    return TopologyState(
        "retrieval.domain.test",
        "1+test",
        (
            Element(
                BoundRef(
                    ElementRef("demo", "retrieval", namespace, "material", "shared-old-id"),
                    "legacy",
                ),
                {
                    "title": title,
                    "snapshot_path": [locator],
                    "edge_ids": [edge_id],
                    "node_ids": [f"node-{edge_id}"],
                },
            ),
        ),
    )


def test_migration_requires_explicit_source_root_before_local_snapshot_reads() -> None:
    result = migrate_legacy_material_states(
        MagicMock(spec=Session),
        "demo",
        (_legacy_state(namespace="shared", title="one", locator="one.txt", edge_id="edge-1"),),
    )

    assert isinstance(result, Failure)
    assert result.code == "INVALID_STRUCTURE"
    assert result.context == {"reason": "source_root_required", "project_key": "demo"}


def test_migration_groups_all_current_placements_before_body_selection(tmp_path, monkeypatch) -> None:
    (tmp_path / "one.txt").write_text("first body", encoding="utf-8")
    (tmp_path / "two.txt").write_text("second body", encoding="utf-8")
    written: list[dict[str, object]] = []

    monkeypatch.setattr(
        "app.services.information_topology.document_materials.persist_terminal_material_in_session",
        lambda _session, payload: (written.append(payload), {"material_id": 81})[1],
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.profile_from_state_payload",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.validate_state",
        lambda *_args, **_kwargs: None,
    )

    result = migrate_legacy_material_states(
        MagicMock(spec=Session),
        "demo",
        (
            _legacy_state(namespace="shared", title="first title", locator="one.txt", edge_id="edge-1"),
            _legacy_state(namespace="shared", title="second title", locator="two.txt", edge_id="edge-2"),
        ),
        source_root=tmp_path,
    )

    assert not isinstance(result, Failure)
    assert len(written) == 1
    assert written[0]["content"] is None
    assert written[0]["title"] is None
    assert written[0]["status"] == "reference_only"
    extracted = written[0]["extracted_data"]
    assert isinstance(extracted, dict)
    assert extracted["migration_decision"] == {
        "title_reason": "placement_title_conflict",
        "body_reason": "body_selection_conflict",
        "selected_source_locator": None,
    }
    assert extracted["legacy_material_identity"] == {
        "project_key": "demo",
        "module_id": "retrieval",
        "namespace": "shared",
        "type_id": "material",
        "local_id": "shared-old-id",
    }
    source_evidence = extracted["migration_source_evidence"]
    assert isinstance(source_evidence, list) and len(source_evidence) == 2
    assert [(record["locator"], record["extraction_status"], record["reason"])
            for record in source_evidence] == [
        ("one.txt", "extracted", None),
        ("two.txt", "extracted", None),
    ]
    assert all(record["mime_type"] == "text/plain" for record in source_evidence)
    assert all(record["extractor"] == "material_input.prepare_material" for record in source_evidence)
    assert all(record["material_text_hash"] is None for record in source_evidence)
    first, second = result
    first_attrs = first.elements[0].attributes
    second_attrs = second.elements[0].attributes
    assert first_attrs["material_ref"] == second_attrs["material_ref"] == material_identity("demo", 81)
    assert first_attrs["placement_title"] == "first title"
    assert second_attrs["placement_title"] == "second title"
    assert first_attrs["edge_ids"] == ["edge-1"]
    assert second_attrs["edge_ids"] == ["edge-2"]
    assert [record["locator"] for record in first_attrs["migration_source_evidence"]] == ["one.txt"]
    assert [record["locator"] for record in second_attrs["migration_source_evidence"]] == ["two.txt"]
    assert "title" not in first_attrs and "title" not in second_attrs


def test_migration_does_not_merge_equal_local_ids_from_different_legacy_namespaces(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "one.txt").write_text("first body", encoding="utf-8")
    (tmp_path / "two.txt").write_text("second body", encoding="utf-8")
    written: list[dict[str, object]] = []
    material_ids = iter((81, 82))

    def write_group(_session, payload):
        written.append(payload)
        return {"material_id": next(material_ids)}

    monkeypatch.setattr(
        "app.services.information_topology.document_materials.persist_terminal_material_in_session",
        write_group,
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.profile_from_state_payload",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.validate_state",
        lambda *_args, **_kwargs: None,
    )

    result = migrate_legacy_material_states(
        MagicMock(spec=Session),
        "demo",
        (
            _legacy_state(namespace="alpha", title="first title", locator="one.txt", edge_id="edge-1"),
            _legacy_state(namespace="beta", title="second title", locator="two.txt", edge_id="edge-2"),
        ),
        source_root=tmp_path,
    )

    assert not isinstance(result, Failure)
    assert [payload["content"] for payload in written] == ["first body", "second body"]
    assert [
        payload["extracted_data"]["legacy_material_identity"]["namespace"]
        for payload in written
    ] == ["alpha", "beta"]
    assert result[0].elements[0].attributes["material_ref"] == material_identity("demo", 81)
    assert result[1].elements[0].attributes["material_ref"] == material_identity("demo", 82)


def test_same_body_reuse_preserves_each_legacy_origin_on_material_and_placement(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "one.txt").write_text("shared body", encoding="utf-8")
    (tmp_path / "two.txt").write_text("shared body", encoding="utf-8")
    created: SimpleNamespace | None = None

    def existing(_session, _project_key, *, uri=None, text_hash=None):
        if text_hash is not None and created is not None and text_hash == created.text_hash:
            return created
        return None

    def write_group(_session, payload):
        nonlocal created
        created = SimpleNamespace(
            id=91,
            text_hash=payload["text_hash"],
            extracted_data=payload["extracted_data"],
        )
        return {"material_id": 91, "inserted": 1}

    monkeypatch.setattr(
        "app.services.information_topology.document_materials._existing_material",
        existing,
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.persist_terminal_material_in_session",
        write_group,
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.profile_from_state_payload",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.validate_state",
        lambda *_args, **_kwargs: None,
    )

    result = migrate_legacy_material_states(
        MagicMock(spec=Session),
        "demo",
        (
            _legacy_state(namespace="alpha", title="first title", locator="one.txt", edge_id="edge-1"),
            _legacy_state(namespace="beta", title="second title", locator="two.txt", edge_id="edge-2"),
        ),
        source_root=tmp_path,
    )

    assert not isinstance(result, Failure)
    assert created is not None
    material_origins = created.extracted_data["migration_source_evidence"]
    assert [(record["locator"], record["legacy_material_identity"]["namespace"])
            for record in material_origins] == [("one.txt", "alpha"), ("two.txt", "beta")]
    assert all(record["material_text_hash"] == sha256(b"shared body").hexdigest()
               for record in material_origins)
    assert result[0].elements[0].attributes["material_ref"] == material_identity("demo", 91)
    assert result[1].elements[0].attributes["material_ref"] == material_identity("demo", 91)
    placement_origins = [
        state.elements[0].attributes["migration_source_evidence"][0]
        for state in result
    ]
    assert [record["legacy_material_identity"]["namespace"] for record in placement_origins] == [
        "alpha", "beta",
    ]


def test_unsupported_snapshot_keeps_hash_mime_status_and_reason_in_one_record(
    tmp_path, monkeypatch
) -> None:
    raw = b"\x00\x01"
    (tmp_path / "unsupported.bin").write_bytes(raw)
    written: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.persist_terminal_material_in_session",
        lambda _session, payload: (written.append(payload), {"material_id": 92, "inserted": 1})[1],
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.profile_from_state_payload",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.validate_state",
        lambda *_args, **_kwargs: None,
    )

    result = migrate_legacy_material_states(
        MagicMock(spec=Session),
        "demo",
        (_legacy_state(
            namespace="unsupported",
            title="unsupported",
            locator="unsupported.bin",
            edge_id="edge-u",
        ),),
        source_root=tmp_path,
    )

    assert not isinstance(result, Failure)
    extracted = written[0]["extracted_data"]
    assert isinstance(extracted, dict)
    record = extracted["migration_source_evidence"][0]
    assert record == {
        "locator": "unsupported.bin",
        "raw_sha256": sha256(raw).hexdigest(),
        "mime_type": "application/octet-stream",
        "extractor": None,
        "extraction_status": "reference_only",
        "reason": "unsupported_mime",
        "snapshot_text_hash": None,
        "material_text_hash": None,
        "selected_for_material_body": False,
        "legacy_material_identity": {
            "project_key": "demo",
            "module_id": "retrieval",
            "namespace": "unsupported",
            "type_id": "material",
            "local_id": "shared-old-id",
        },
    }
    assert result[0].elements[0].attributes["migration_source_evidence"] == [record]


def test_existing_material_is_unchanged_and_origin_evidence_stays_on_placement(
    monkeypatch,
) -> None:
    extracted_data = {"owner": "existing"}
    existing = SimpleNamespace(
        id=93,
        title="existing title",
        content="existing body",
        uri="source.txt",
        text_hash=sha256(b"existing body").hexdigest(),
        extracted_data=extracted_data,
    )
    session = MagicMock(spec=Session)
    session.execute.return_value.scalars.return_value.all.return_value = [existing]
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.persist_terminal_material_in_session",
        lambda *_args, **_kwargs: pytest.fail("existing Material must not be rewritten"),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.profile_from_state_payload",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.validate_state",
        lambda *_args, **_kwargs: None,
    )

    result = migrate_legacy_material_states(
        session,
        "demo",
        (_legacy_state(namespace="existing", title="legacy", locator="source.txt", edge_id="edge-e"),),
    )

    assert not isinstance(result, Failure)
    assert (existing.title, existing.content, existing.uri, existing.text_hash) == (
        "existing title",
        "existing body",
        "source.txt",
        sha256(b"existing body").hexdigest(),
    )
    assert existing.extracted_data is extracted_data
    evidence = result[0].elements[0].attributes["migration_source_evidence"]
    assert evidence[0]["reason"] == "existing_material_uri"
    assert evidence[0]["legacy_material_identity"]["namespace"] == "existing"


def test_migration_reads_one_safe_snapshot_and_calls_the_original_in_session_writer(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "source.txt").write_text("canonical body", encoding="utf-8")
    session = MagicMock(spec=Session)
    session.execute.return_value.scalars.return_value.all.return_value = []
    session.query.return_value.filter.return_value.first.return_value = None

    def assign_identity(row: object) -> None:
        setattr(row, "id", 91)

    session.add.side_effect = assign_identity
    monkeypatch.setattr(
        "app.services.ingest.terminal_writer.get_or_create_source",
        lambda *_args, **_kwargs: SimpleNamespace(id=7),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.profile_from_state_payload",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "app.services.information_topology.document_materials.validate_state",
        lambda *_args, **_kwargs: None,
    )

    result = migrate_legacy_material_states(
        session,
        "demo",
        (_legacy_state(namespace="shared", title="one title", locator="source.txt", edge_id="edge-1"),),
        source_root=tmp_path,
    )

    assert not isinstance(result, Failure)
    inserted = session.add.call_args.args[0]
    assert inserted.content == "canonical body"
    assert inserted.title == "one title"
    assert inserted.uri == "source.txt"
    assert inserted.text_hash == sha256(b"canonical body").hexdigest()
    assert result[0].elements[0].attributes["material_ref"] == material_identity("demo", 91)


def test_merge_wrapper_rolls_back_the_owned_transaction_when_core_returns_failure(monkeypatch) -> None:
    session = MagicMock(spec=Session)
    session.__enter__.return_value = session
    transaction = MagicMock()
    transaction.__enter__.return_value = None
    transaction.__exit__.return_value = False
    session.begin.return_value = transaction
    service = object.__new__(InformationTopologyService)
    service.dependencies = SimpleNamespace(session_factory=lambda: session)
    failure = topology_failures.fail(
        "INVALID_STRUCTURE",
        "local snapshot migration requires an explicit source root",
        {"reason": "source_root_required", "project_key": "demo"},
    )
    monkeypatch.setattr(service, "merge_materials_in_session", lambda *_args, **_kwargs: failure)

    result = service.merge_materials("demo")

    assert result is failure
    exc_type = transaction.__exit__.call_args.args[0]
    assert exc_type is not None and issubclass(exc_type, Exception)
