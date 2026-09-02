"""Fail-closed P0-C harness scope and acceptance-coverage boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from .p0c_postgres_fixture import (
    DATABASE_ENV,
    SEED_CONTENT_BYTES,
    SEED_CONTENT_SHA256,
    SEED_STATEMENT_SHA256,
    _require_dedicated_database_url,
    frozen_document_seed_statements,
)

pytestmark = pytest.mark.contract

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]

P0C_LIVE_FILES = (
    HERE / "test_p0c_submission_postgres.py",
    HERE / "test_p0c_two_nodes_postgres.py",
    HERE / "test_p0c_vertical_specimen_postgres.py",
    HERE / "test_p0c_delivery_recovery_postgres.py",
)

# A01-A10 are the first ten frozen first-specimen acceptances.  A11/A12 are
# projection rebuild and gap-to-successor materialization, owned by P0-D.
ACCEPTANCE_DISPOSITION = {
    **{f"A{index:02d}": "P0_C_LIVE" for index in range(1, 11)},
    "A11": "P0_D_ONLY_NOT_CLAIMED",
    "A12": "P0_D_ONLY_NOT_CLAIMED",
}


def test_database_url_guard_rejects_default_and_non_test_databases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for url in (
        "postgresql+psycopg2:///postgres",
        "postgresql+psycopg2:///market_research_workflow",
        "sqlite:///successor_test.db",
    ):
        monkeypatch.setenv(DATABASE_ENV, url)
        with pytest.raises(pytest.fail.Exception):
            _require_dedicated_database_url()


def test_frozen_seed_101_102_statements_and_known_content_contract_are_pinned() -> None:
    statements = frozen_document_seed_statements()
    assert set(statements) == {101, 102}
    assert SEED_STATEMENT_SHA256 == {
        101: "2d784235fbd94613e46782e2016eb7ddebf42e14f1779885ebbaf4576699bb93",
        102: "80ae76aac30d1670b3838079534f550bc01c39f3747428f9b533f99093c812ab",
    }
    assert SEED_CONTENT_BYTES == {101: 1153, 102: 50009}
    assert SEED_CONTENT_SHA256 == {
        101: "409789283ff6ee8aabcd5924866199cc6f9bb26f957a99f854708bd4aabb3c40",
        102: "0494ea262e1577dc00cb3241341c4ab8bfe155b5601d61be7bee70407cc4ea6b",
    }


def test_a01_a10_and_cw01_cw10_have_named_live_postgres_evidence() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in P0C_LIVE_FILES
    )
    for index in range(1, 11):
        assert f"a{index:02d}" in source, f"A{index:02d} lacks named P0-C evidence"
        assert f"cw{index:02d}" in source, f"CW{index:02d} lacks named P0-C evidence"
    assert ACCEPTANCE_DISPOSITION["A11"] == "P0_D_ONLY_NOT_CLAIMED"
    assert ACCEPTANCE_DISPOSITION["A12"] == "P0_D_ONLY_NOT_CLAIMED"
    assert "test_a11" not in source
    assert "test_a12" not in source


def test_runtime_harness_never_reopens_legacy_documents_after_submission() -> None:
    adapter_name = "PostgresLegacyDocumentCanonicalReadAdapter"
    runtime_files = (
        HERE / "test_p0c_two_nodes_postgres.py",
        HERE / "test_p0c_vertical_specimen_postgres.py",
        HERE / "test_p0c_delivery_recovery_postgres.py",
    )
    for path in runtime_files:
        assert adapter_name not in path.read_text(encoding="utf-8"), path.name
    fixture = (HERE / "p0c_postgres_fixture.py").read_text(encoding="utf-8")
    assert fixture.count(adapter_name) >= 2
    assert "document_port=" in fixture


def test_successor_runtime_has_no_legacy_service_or_migration_import() -> None:
    runtime_root = BACKEND / "app" / "successor_runtime"
    forbidden = (
        "app.services",
        "app.successor_migration",
        "import celery",
        "import redis",
    )
    for path in runtime_root.rglob("*.py"):
        relative = path.relative_to(runtime_root)
        if relative.parts and relative.parts[0] == "specification":
            # Family fragment configs are deterministic evidence/CLI glue that
            # deliberately read legacy adapters to build observations.  The
            # production runtime boundary below remains enforced for every
            # other module under app/successor_runtime.
            continue
        source = path.read_text(encoding="utf-8")
        for fragment in forbidden:
            assert fragment not in source, f"{path} imports {fragment}"


def test_live_harness_contains_no_network_provider_or_external_delivery_call() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in P0C_LIVE_FILES)
    forbidden_calls = (
        "requests.",
        "httpx.",
        "urllib.request",
        "boto3.",
        "OpenAI(",
        "external_delivery(",
    )
    for fragment in forbidden_calls:
        assert fragment not in source
    assert "internal-export://" in source
