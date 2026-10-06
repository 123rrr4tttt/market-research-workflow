from __future__ import annotations

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
        patch("app.services.crawlers.scrapyd_result_ingest.run_raw_import_documents") as writer,
    ):
        result = ingest_scrapyd_job_output(
            project_key="demo_proj",
            scrapy_project="crawler_demo",
            job_id="job-failed",
        )

    assert result["status"] == "finished_failed"
    assert result["raw_item_count"] == 0
    writer.assert_not_called()
