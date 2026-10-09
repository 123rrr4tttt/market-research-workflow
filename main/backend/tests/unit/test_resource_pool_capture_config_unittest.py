from __future__ import annotations

import contextlib

import pytest
from app.models.entities import ResourcePoolCaptureConfig
from app.services.resource_pool import capture_config

pytestmark = pytest.mark.unit


class _Session:
    row: ResourcePoolCaptureConfig | None = None
    commits = 0

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _statement: object) -> _Session:
        return self

    def scalar_one_or_none(self) -> ResourcePoolCaptureConfig | None:
        return self.row

    def add(self, row: ResourcePoolCaptureConfig) -> None:
        self.row = row

    def commit(self) -> None:
        self.commits += 1


def _bind_public_schema(_schema: str) -> contextlib.AbstractContextManager[None]:
    return contextlib.nullcontext()


def test_capture_config_native_model_insert_update_and_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    monkeypatch.setattr(capture_config, "SessionLocal", lambda: session)
    monkeypatch.setattr(capture_config, "bind_schema", _bind_public_schema)

    inserted = capture_config.upsert_capture_config(
        "demo_proj",
        job_types=["ingest"],
        scope="project",
        enabled=True,
    )
    assert isinstance(session.row, ResourcePoolCaptureConfig)
    assert session.row.project_key == "demo_proj"
    assert inserted == {
        "project_key": "demo_proj",
        "job_types": ["ingest"],
        "scope": "project",
        "enabled": True,
    }

    updated = capture_config.upsert_capture_config(
        "demo_proj",
        job_types=["discovery", "crawl"],
        scope="shared",
        enabled=False,
    )
    assert updated["scope"] == "shared"
    assert session.row.job_types == ["discovery", "crawl"]
    assert capture_config.get_capture_config("demo_proj") == {
        "job_types": ["discovery", "crawl"],
        "scope": "shared",
        "enabled": False,
    }
    assert session.commits == 2
