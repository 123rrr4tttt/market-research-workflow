from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import tasks

pytestmark = pytest.mark.unit


def _deploy_kwargs() -> dict[str, object]:
    return {
        "deploy_run_id": 71,
        "project_key": "demo_proj",
        "scrapy_project": "crawler_demo",
        "spider": "example",
        "channel_key": "crawler.demo",
        "item_key": "crawler.demo.default",
        "version": "v1",
    }


def test_orchestrated_deploy_completes_original_deploy_run() -> None:
    with (
        patch(
            "app.services.tasks._execute_register_source_library_scrapy_binding",
            return_value={"channel_registered": True, "item_registered": True},
        ),
        patch("app.services.crawlers_mgmt.finalize_deploy_run") as finalize,
    ):
        result = tasks.task_orchestrate_crawler_deploy.run(**_deploy_kwargs())

    assert result["register"]["item_registered"] is True
    finalize.assert_called_once_with(71, status="succeeded")


def test_orchestrated_deploy_fails_original_deploy_run() -> None:
    with (
        patch(
            "app.services.tasks._execute_register_source_library_scrapy_binding",
            side_effect=RuntimeError("registration failed"),
        ),
        patch("app.services.crawlers_mgmt.finalize_deploy_run") as finalize,
    ):
        with pytest.raises(RuntimeError, match="registration failed"):
            tasks.task_orchestrate_crawler_deploy.run(**_deploy_kwargs())

    finalize.assert_called_once_with(71, status="failed", error="registration failed")
