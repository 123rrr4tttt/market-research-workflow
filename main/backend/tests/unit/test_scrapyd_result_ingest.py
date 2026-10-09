from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.services.crawlers.scrapyd_result_ingest import ingest_scrapyd_job_output


pytestmark = pytest.mark.unit


def test_failed_scrapyd_job_never_writes_partial_items() -> None:
    client = Mock()
    client.list_jobs.return_value = {
        "pending": [],
        "running": [],
        "finished": [{"id": "job-failed", "status": "failed"}],
    }
    with (
        patch(
            "app.services.crawlers.scrapyd_result_ingest.ensure_scrapyd_ready",
            return_value="http://scrapyd.test",
        ),
        patch("app.services.crawlers.scrapyd_result_ingest.ScrapydClient", return_value=client),
        patch("app.services.crawlers.scrapyd_result_ingest.run_raw_import_materials") as writer,
    ):
        result = ingest_scrapyd_job_output(
            project_key="demo_proj",
            scrapy_project="crawler_demo",
            job_id="job-failed",
        )

    assert result["status"] == "finished_failed"
    assert result["raw_item_count"] == 0
    writer.assert_not_called()


def test_typed_crawler_request_reaches_canonical_material_import() -> None:
    from app.composition.source_library import ScrapydCrawlerOutputIngestPort
    from app.services.source_library.provider_ports import CrawlerOutputIngestRequest

    client = Mock()
    client.list_jobs.return_value = {
        "pending": [],
        "running": [],
        "finished": [
            {
                "id": "job-completed",
                "status": "finished",
                "items_url": "/items/job-completed.jl",
            }
        ],
    }
    response = Mock()
    response.text = (
        '{"title":"Material title","content":"Material body",'
        '"url":"https://example.test/material"}\n'
    )
    http = Mock()
    http.get.return_value = response
    http_context = Mock()
    http_context.__enter__ = Mock(return_value=http)
    http_context.__exit__ = Mock(return_value=False)
    writer_result = {"inserted": 1, "updated": 0, "skipped": 0, "error_count": 0}

    request = CrawlerOutputIngestRequest(
        provider_type="scrapy",
        project_key="demo_proj",
        provider_project="crawler_demo",
        provider_job_id="job-completed",
        base_url="http://scrapyd.test",
        wait_timeout_seconds=8.0,
        poll_interval_seconds=0.5,
        source_name="crawler.demo_proj",
        material_type="news",
        enable_extraction=False,
        max_items=10,
    )
    with (
        patch(
            "app.services.crawlers.scrapyd_result_ingest.ensure_scrapyd_ready",
            return_value="http://scrapyd.test",
        ),
        patch("app.services.crawlers.scrapyd_result_ingest.ScrapydClient", return_value=client),
        patch("app.services.crawlers.scrapyd_result_ingest.httpx.Client", return_value=http_context),
        patch(
            "app.services.crawlers.scrapyd_result_ingest.bind_project",
            return_value=nullcontext(),
        ),
        patch(
            "app.services.crawlers.scrapyd_result_ingest.run_raw_import_materials",
            return_value=writer_result,
        ) as writer,
    ):
        result = ScrapydCrawlerOutputIngestPort().ingest(request)

    assert result.status == "ingested"
    assert result.payload["import_result"] == writer_result
    writer.assert_called_once_with(
        payload={
            "source_name": "crawler.demo_proj",
            "default_material_type": "news",
            "enable_extraction": False,
            "items": [
                {
                    "text": "Material body",
                    "title": "Material title",
                    "uri": "https://example.test/material",
                    "material_type": "news",
                }
            ],
        },
        project_key="demo_proj",
    )


def test_scrapy_binding_registers_canonical_material_output_config() -> None:
    from app.services.crawlers_mgmt.orchestration import (
        register_or_update_source_library_scrapy_binding,
    )

    channel = SimpleNamespace(
        kind=None,
        provider=None,
        provider_config=None,
        execution_policy=None,
        default_params=None,
        param_schema=None,
        extra=None,
    )
    item = SimpleNamespace(params=None, tags=None, extra=None)
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: channel),
        SimpleNamespace(scalar_one_or_none=lambda: item),
    ]

    with (
        patch(
            "app.services.crawlers_mgmt.orchestration.bind_project",
            return_value=nullcontext(),
        ),
        patch(
            "app.services.crawlers_mgmt.orchestration.SessionLocal",
            return_value=session,
        ),
    ):
        result = register_or_update_source_library_scrapy_binding(
            project_key="demo_proj",
            channel_key="crawler.demo",
            item_key="crawler.demo.news",
            spider="news_spider",
            scrapy_project="crawler_runtime",
        )

    assert result["item_registered"] is True
    assert item.params["output_ingest"] == {
        "enabled": True,
        "material_type": "news",
        "enable_extraction": False,
        "wait_timeout_seconds": 120.0,
        "poll_interval_seconds": 0.5,
        "max_items": 100,
    }
    assert "doc_type" not in item.params["output_ingest"]
    session.commit.assert_called_once_with()
