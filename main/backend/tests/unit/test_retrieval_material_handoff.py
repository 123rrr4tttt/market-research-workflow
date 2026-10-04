from __future__ import annotations

from datetime import date
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.services.ingest.material_input import (
    FetchedResource,
    GivenContent,
    MaterialPreparationError,
    ResourceRef,
    prepare_material,
    prepare_resource_via_http_port,
)
from app.services.ingest.material_ingress import (
    MaterialSourceContext,
    MaterialTargetSpec,
    build_material_frontdoor_payload,
)
from app.successor_runtime.capabilities.material_ingest_movements import RawSnapshot


pytestmark = pytest.mark.unit


def test_given_text_keeps_exact_raw_digest_and_requires_no_fetch():
    def unexpected_fetch(_url: str) -> FetchedResource:
        pytest.fail("given content must not be downloaded")

    raw = "  Existing text\n".encode()
    prepared = prepare_material(GivenContent(raw), fetch_resource=unexpected_fetch)

    assert prepared.input_kind == "given"
    assert prepared.raw_bytes == raw
    assert prepared.raw_content_digest == sha256(raw).hexdigest()
    assert prepared.text == "Existing text"
    assert prepared.snapshot_ref is None


def test_resource_locator_is_not_body_and_uses_supplied_fetch_port():
    calls: list[str] = []

    def fetch(url: str) -> FetchedResource:
        calls.append(url)
        return FetchedResource(b"actual response body", "text/plain; charset=utf-8", url)

    with pytest.raises(MaterialPreparationError, match="fetch port is required"):
        prepare_material(ResourceRef("https://example.test/report"))
    prepared = prepare_material(ResourceRef("https://example.test/report"), fetch_resource=fetch)

    assert calls == ["https://example.test/report"]
    assert prepared.text == "actual response body"
    assert prepared.text != "https://example.test/report"
    assert prepared.input_kind == "resource"


def test_resource_adapter_uses_registered_fetch_response_bytes(monkeypatch):
    from app.services.resource_pool import http_port

    calls = []

    def fetch_html(url, *, timeout, retries):
        calls.append((url, timeout, retries))
        response = SimpleNamespace(
            content=b"fetched text",
            headers={"Content-Type": "text/plain; charset=utf-8"},
            final_url="https://example.test/final",
        )
        return "ignored parser projection", response

    monkeypatch.setattr(http_port, "fetch_html", fetch_html)
    prepared = prepare_resource_via_http_port(ResourceRef("https://example.test/redirect"))

    assert calls == [("https://example.test/redirect", 8.0, 1)]
    assert prepared.source_locator == "https://example.test/final"
    assert prepared.raw_bytes == b"fetched text"


def test_existing_snapshot_reuses_identity_and_never_fetches():
    snapshot = RawSnapshot(
        project_key="project-a",
        source_locator="https://example.test/source",
        raw_bytes=b"snapshot body",
        mime_type="text/plain",
    )

    def unexpected_fetch(_url: str) -> FetchedResource:
        pytest.fail("existing snapshot must not be downloaded")

    prepared = prepare_material(snapshot, fetch_resource=unexpected_fetch)

    assert prepared.input_kind == "snapshot"
    assert prepared.snapshot_ref == snapshot.snapshot_ref
    assert prepared.snapshot_identity_digest == snapshot.snapshot_identity_digest
    assert prepared.raw_content_digest == snapshot.raw_content_digest


@pytest.mark.parametrize(
    "given,match",
    [
        (GivenContent(b"%PDF-1.7", mime_type="application/pdf"), "unsupported"),
        (GivenContent(b"\xff", mime_type="text/plain"), "UTF-8"),
        (GivenContent(b"  "), "empty"),
        (GivenContent(b"<html>body</html>", mime_type="text/html"), "unsupported"),
    ],
)
def test_preparation_rejects_unsupported_or_invalid_bytes(given, match):
    with pytest.raises(MaterialPreparationError, match=match):
        prepare_material(given)


def test_unsupported_material_input_is_programmer_error():
    with pytest.raises(TypeError, match="unsupported material input"):
        prepare_material(object())


def test_frontdoor_payload_is_pure_and_uses_target_and_source_decisions():
    prepared = prepare_material(GivenContent.from_text("  Given report  "))
    payload = build_material_frontdoor_payload(
        prepared,
        target=MaterialTargetSpec(
            doc_type="raw_note",
            title="Given report",
            summary=None,
            publish_date=date(2026, 9, 24),
            state=None,
            extraction_enabled=False,
            extraction_mode="comprehensive",
            chunks=("Given report",),
            extraction_flags={"include_policy": True},
        ),
        source=MaterialSourceContext(
            source_name="user",
            source_kind="manual",
            uri=None,
            platform="raw_import",
            entrypoint="ingest.raw_import",
            source_mode="raw_import",
        ),
        extracted_data_base={"_raw_input": {"raw_content_digest": prepared.raw_content_digest}},
    )

    candidate = payload["document_candidate"]
    assert candidate["content"] == "Given report"
    assert candidate["text_hash"] == sha256(b"Given report").hexdigest()
    assert candidate["publish_date"] == date(2026, 9, 24)
    assert payload["terminal_context"]["ingestion_entrypoint"] == "ingest.raw_import"
    assert payload["extraction_plan"]["enabled"] is False
    assert payload["extraction_plan"]["include_policy"] is True
    assert payload["extraction_plan"]["include_market"] is False


def test_raw_import_given_text_reaches_existing_frontdoor_without_fetch(monkeypatch):
    from app.services.ingest import raw_import

    class Scalar:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class Session:
        def __init__(self):
            self.calls = 0
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            self.calls += 1
            return Scalar(None)

        def commit(self):
            self.committed = True

    session = Session()
    observed = []
    monkeypatch.setattr(raw_import, "SessionLocal", lambda: session)
    monkeypatch.setattr(raw_import, "start_job", lambda *_args, **_kwargs: 11)
    monkeypatch.setattr(raw_import, "complete_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        raw_import,
        "fetch_html",
        lambda *_args, **_kwargs: pytest.fail("given text without URL must not fetch"),
    )

    def postprocess(*, ingress_envelope, run_writer):
        observed.append((ingress_envelope, run_writer))
        return {"data": {"writer_result": {"inserted": 1, "doc_id": 42}}}

    monkeypatch.setattr(raw_import, "run_postprocess_frontdoor", postprocess)
    result = raw_import.run_raw_import_documents(
        {
            "items": [{
                "text": "  Given report  ",
                "uri": "https://example.test/provenance",
                "material_input_kind": "given",
                "doc_type": "raw_note",
            }],
            "enable_extraction": False,
        },
        "project-a",
    )

    assert result["inserted"] == 1
    assert result["error_count"] == 0
    assert session.committed
    assert len(observed) == 1 and observed[0][1] is True
    payload = observed[0][0]["collection_payload"]
    assert payload["document_candidate"]["content"] == "Given report"
    assert payload["document_candidate"]["uri"] == "https://example.test/provenance"
    assert payload["document_candidate"]["text_hash"] == sha256(b"Given report").hexdigest()
    assert payload["document_candidate"]["extracted_data_base"]["_raw_input"]["material_input"]["raw_content_digest"] == sha256(b"  Given report  ").hexdigest()


def _install_raw_import_observation(monkeypatch, *, fetch_html, writer_result):
    from app.services.ingest import raw_import

    class Scalar:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return Scalar(None)

        def commit(self):
            return None

    observed = []
    monkeypatch.setattr(raw_import, "SessionLocal", lambda: Session())
    monkeypatch.setattr(raw_import, "start_job", lambda *_args, **_kwargs: 21)
    monkeypatch.setattr(raw_import, "complete_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(raw_import, "fetch_html", fetch_html)
    monkeypatch.setattr(
        raw_import,
        "run_postprocess_frontdoor",
        lambda *, ingress_envelope, run_writer: (
            observed.append(ingress_envelope),
            writer_result,
        )[1],
    )
    return observed


@pytest.mark.parametrize(
    ("content_type", "expected_mime"),
    [
        ("text/plain; charset=utf-8", "text/plain"),
        ("text/markdown; charset=utf-8", "text/markdown"),
    ],
)
def test_raw_import_explicit_text_resource_preserves_large_exact_body_with_one_fetch(
    monkeypatch, content_type, expected_mime
):
    from app.services.ingest import raw_import

    body = (
        "RFC section: an angle-bracket reference <https://example.test/source>.\n\n"
        "Short URL paragraph.\n\n"
    ) * 5000
    raw_bytes = body.encode("utf-8")
    calls = []

    def fetch_html(url, *, timeout, retries):
        calls.append((url, timeout, retries))
        response = SimpleNamespace(
            content=raw_bytes,
            headers={"Content-Type": content_type},
            status_code=200,
            final_url="https://example.test/final-rfc",
        )
        return "parser projection must not rewrite explicit plain text", response

    observed = _install_raw_import_observation(
        monkeypatch,
        fetch_html=fetch_html,
        writer_result={"data": {"writer_result": {"inserted": 1, "doc_id": 77}}},
    )
    result = raw_import.run_raw_import_documents(
        {
            "items": [{"uri": "https://example.test/rfc"}],
            "enable_extraction": False,
            "max_chunks": 8,
        },
        "project-a",
    )

    assert result["inserted"] == 1
    assert calls == [("https://example.test/rfc", 8.0, 1)]
    payload = observed[0]["collection_payload"]
    candidate = payload["document_candidate"]
    material = candidate["extracted_data_base"]["_raw_input"]["material_input"]
    assert candidate["content"] == body.strip()
    assert len(candidate["content"]) > 400000
    assert candidate["uri"] == "https://example.test/rfc"
    assert material == {
        "kind": "resource",
        "raw_content_digest": sha256(raw_bytes).hexdigest(),
        "mime_type": expected_mime,
    }
    assert len(payload["extraction_plan"]["chunks"]) <= 8
    assert candidate["extracted_data_base"]["_raw_input"]["truncated_for_extraction"] is True


def test_raw_import_missing_content_type_keeps_html_extraction_and_one_fetch(monkeypatch):
    from app.services.ingest import raw_import

    html = (
        "<html><head><title>HTML source</title></head><body>"
        "<nav>Navigation shell</nav><article>"
        + ("Stable article body from HTML. " * 5)
        + "</article></body></html>"
    )
    calls = []

    def fetch_html(url, *, timeout, retries):
        calls.append(url)
        return html, SimpleNamespace(status_code=200, final_url=url)

    observed = _install_raw_import_observation(
        monkeypatch,
        fetch_html=fetch_html,
        writer_result={"data": {"writer_result": {"inserted": 1, "doc_id": 78}}},
    )
    raw_import.run_raw_import_documents(
        {"items": [{"uri": "https://example.test/html"}], "enable_extraction": False},
        "project-a",
    )

    assert calls == ["https://example.test/html"]
    candidate = observed[0]["collection_payload"]["document_candidate"]
    assert candidate["content"] == ("Stable article body from HTML. " * 5).rstrip()
    assert candidate["extracted_data_base"]["_raw_input"]["fetched_from_url"] is True
    assert "material_input" not in candidate["extracted_data_base"]["_raw_input"]


def test_raw_import_mixed_given_and_plain_url_preserves_merge_semantics(monkeypatch):
    from app.services.ingest import raw_import

    plain_url_body = "Plain URL response with <https://example.test/inline>."
    calls = []

    def fetch_html(url, *, timeout, retries):
        calls.append(url)
        return plain_url_body, SimpleNamespace(
            content=plain_url_body.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            status_code=200,
            final_url="https://example.test/final",
        )

    observed = _install_raw_import_observation(
        monkeypatch,
        fetch_html=fetch_html,
        writer_result={"data": {"writer_result": {"inserted": 1, "doc_id": 79}}},
    )
    raw_import.run_raw_import_documents(
        {
            "items": [{"text": "Given note.", "uri": "https://example.test/source"}],
            "enable_extraction": False,
        },
        "project-a",
    )

    assert calls == ["https://example.test/source"]
    candidate = observed[0]["collection_payload"]["document_candidate"]
    assert candidate["content"] == (
        "Given note.\n\n[URL_CONTENT]\n" + plain_url_body
    )
    assert candidate["uri"] == "https://example.test/source"
    assert candidate["extracted_data_base"]["_raw_input"]["fetched_from_url"] is True
    assert "material_input" not in candidate["extracted_data_base"]["_raw_input"]


def test_raw_import_overwrite_from_plain_to_html_clears_stale_material_witness(monkeypatch):
    from app.services.ingest import raw_import

    existing = SimpleNamespace(
        id=80,
        source_id=1,
        state=None,
        doc_type="market_info",
        title=None,
        publish_date=None,
        content="old",
        summary=None,
        text_hash="old",
        uri="https://example.test/source",
        updated_at=None,
        extracted_data={
            "_raw_input": {
                "material_input": {
                    "kind": "resource",
                    "raw_content_digest": "a" * 64,
                    "mime_type": "text/plain",
                }
            },
            "preserved_existing_projection": True,
        },
    )

    class Scalar:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return Scalar(existing)

        def commit(self):
            return None

    html = (
        "<html><body><article>"
        + ("Replacement HTML article body. " * 6)
        + "</article></body></html>"
    )
    observed = []
    monkeypatch.setattr(raw_import, "SessionLocal", lambda: Session())
    monkeypatch.setattr(raw_import, "start_job", lambda *_args, **_kwargs: 22)
    monkeypatch.setattr(raw_import, "complete_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(raw_import, "fetch_html", lambda *_args, **_kwargs: (html, SimpleNamespace(status_code=200, final_url="https://example.test/source")))
    monkeypatch.setattr(raw_import, "_get_or_create_source", lambda *_args, **_kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(
        raw_import,
        "run_postprocess_frontdoor",
        lambda *, ingress_envelope, run_writer: (
            observed.append(ingress_envelope),
            {"data": {"normalized_payload": {"extracted_data": existing.extracted_data}}},
        )[1],
    )

    result = raw_import.run_raw_import_documents(
        {
            "items": [{"uri": "https://example.test/source"}],
            "overwrite_on_uri": True,
            "enable_extraction": False,
        },
        "project-a",
    )

    assert result["updated"] == 1
    raw_input = observed[0]["collection_payload"]["document_candidate"]["extracted_data_base"]["_raw_input"]
    assert "material_input" not in raw_input
    assert raw_input["fetched_from_url"] is True
    assert observed[0]["collection_payload"]["document_candidate"]["extracted_data_base"]["preserved_existing_projection"] is True


def test_raw_import_invalid_utf8_plain_resource_is_not_success(monkeypatch):
    from app.services.ingest import raw_import

    calls = []

    def fetch_html(url, *, timeout, retries):
        calls.append(url)
        return b"\xff", SimpleNamespace(
            content=b"\xff",
            headers={"Content-Type": "text/plain; charset=utf-8"},
            status_code=200,
            final_url=url,
        )

    observed = _install_raw_import_observation(
        monkeypatch,
        fetch_html=fetch_html,
        writer_result={"data": {"writer_result": {"inserted": 1}}},
    )
    result = raw_import.run_raw_import_documents(
        {"items": [{"uri": "https://example.test/invalid"}], "enable_extraction": False},
        "project-a",
    )

    assert calls == ["https://example.test/invalid"]
    assert observed == []
    assert result["inserted"] == 0
    assert result["error_count"] == 0
    assert result["items"][0]["status"] == "skipped_empty_text"
    assert "valid UTF-8" in result["items"][0]["fetch_url_error"]
