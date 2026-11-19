from __future__ import annotations

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import JSON, BigInteger, Integer, MetaData, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from app.models.entities import CrawlerDeployRun, CrawlerProject
from app.services import tasks
from app.services.crawlers_mgmt import service

pytestmark = pytest.mark.unit


@pytest.fixture
def crawler_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    engine = create_engine("sqlite+pysqlite:///:memory:").execution_options(schema_translate_map={"public": None})
    metadata = MetaData()
    for model in (CrawlerProject, CrawlerDeployRun):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, BigInteger):
                column.type = Integer()
            elif isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(service, "SessionLocal", sessions)
    with sessions() as session:
        session.add(CrawlerProject(
            project_key="crawler_demo",
            name="Example crawler",
            provider="scrapyd",
            status="deployed",
            current_version="v3",
            deployed_version="v2",
            previous_version="v1",
            import_payload={"egg_content_b64": "art-placeholder"},
        ))
        session.commit()
    try:
        yield
    finally:
        engine.dispose()


def _assert_versions(deployed: str, previous: str) -> None:
    project = service.get_project(project_key="crawler_demo")
    assert project is not None
    assert (project["deployed_version"], project["previous_version"]) == (deployed, previous)


def _submit_deploy(
    monkeypatch: pytest.MonkeyPatch,
    *,
    callback: Callable[..., SimpleNamespace] | Exception | None = None,
):
    delay = Mock(side_effect=callback, return_value=SimpleNamespace(id="deploy-task-71"))
    monkeypatch.setattr(tasks.task_orchestrate_crawler_deploy, "delay", delay)
    response = service.deploy_project(
        project_key="crawler_demo",
        async_mode=True,
        registration_project_key="demo_proj",
    )
    return response, delay.call_args.kwargs


def test_original_worker_receipt_is_required_to_advance_version(crawler_store, monkeypatch):
    deploy = Mock(return_value={"provider_status": "ok", "version": "v3"})
    register = Mock(return_value={"channel_registered": True, "item_registered": True})
    monkeypatch.setattr(tasks, "_execute_crawler_deploy_version", deploy)
    monkeypatch.setattr(tasks, "_execute_register_source_library_scrapy_binding", register)

    response, worker_args = _submit_deploy(monkeypatch)
    run_id = response["run"]["id"]
    assert response["task_id"] == response["run"]["external_job_id"] == "deploy-task-71"
    assert response["run"]["status"] == "queued"
    assert response["run"]["from_version"] == "v2"
    assert response["run"]["to_version"] == "v3"
    assert response["run"]["finished_at"] is None
    _assert_versions("v2", "v1")

    tasks.task_orchestrate_crawler_deploy.run(**worker_args)

    receipt = service.get_deploy_run(run_id)
    assert receipt is not None
    assert receipt["status"] == "succeeded"
    assert receipt["finished_at"]
    assert receipt["external_job_id"] == "deploy-task-71"
    assert deploy.call_args.kwargs["version"] == "v3"
    assert register.call_args.kwargs["project_key"] == "demo_proj"
    _assert_versions("v3", "v2")

    assert service.finalize_deploy_run(run_id, status="failed") == receipt
    _assert_versions("v3", "v2")

    _, replay_worker_args = _submit_deploy(monkeypatch)
    tasks.task_orchestrate_crawler_deploy.run(**replay_worker_args)
    _assert_versions("v3", "v2")


def test_registration_only_is_terminal_without_a_version_write(crawler_store, monkeypatch):
    deploy = Mock()
    register = Mock(return_value={"channel_registered": True, "item_registered": True})
    monkeypatch.setattr(tasks, "_execute_crawler_deploy_version", deploy)
    monkeypatch.setattr(tasks, "_execute_register_source_library_scrapy_binding", register)
    service.import_project({"project_key": "crawler_demo", "version": "v3"})
    response, worker_args = _submit_deploy(monkeypatch)

    outcome = tasks.task_orchestrate_crawler_deploy.run(**worker_args)

    assert outcome["deploy"]["provider_status"] == "skipped_no_artifact"
    register.assert_called_once()
    deploy.assert_not_called()
    receipt = service.get_deploy_run(response["run"]["id"])
    assert receipt is not None
    assert receipt["status"] == "registered"
    assert receipt["finished_at"]
    _assert_versions("v2", "v1")


@pytest.mark.parametrize(
    ("provider_receipt", "fail_registration", "error"),
    [
        ({"provider_status": "queued", "version": "v3"}, False, "did not confirm"),
        ({"provider_status": "ok", "version": "v1"}, False, "did not confirm"),
        ({"provider_status": "ok", "version": "v3"}, True, "registration failed"),
    ],
)
def test_incomplete_worker_receipt_preserves_versions(
    crawler_store, monkeypatch, provider_receipt, fail_registration, error,
):
    register = Mock(side_effect=RuntimeError(error) if fail_registration else None)
    monkeypatch.setattr(tasks, "_execute_crawler_deploy_version", Mock(return_value=provider_receipt))
    monkeypatch.setattr(tasks, "_execute_register_source_library_scrapy_binding", register)
    response, worker_args = _submit_deploy(monkeypatch)

    with pytest.raises((ValueError, RuntimeError), match=error):
        tasks.task_orchestrate_crawler_deploy.run(**worker_args)

    assert register.call_count == int(fail_registration)
    receipt = service.get_deploy_run(response["run"]["id"])
    assert receipt is not None
    assert receipt["status"] == "failed"
    assert receipt["finished_at"]
    assert error in receipt["error"]
    _assert_versions("v2", "v1")


def test_dispatch_failure_is_not_a_version_write(crawler_store, monkeypatch):
    response, _ = _submit_deploy(monkeypatch, callback=RuntimeError("broker unavailable"))

    assert response["task_id"] is None
    assert response["run"]["status"] == "failed"
    assert response["run"]["error"] == "broker unavailable"
    assert response["run"]["finished_at"]
    _assert_versions("v2", "v1")


def test_fast_worker_receipt_is_read_back_without_being_overwritten(crawler_store, monkeypatch):
    monkeypatch.setattr(tasks, "_execute_crawler_deploy_version", Mock(
        return_value={"provider_status": "ok", "version": "v3"},
    ))
    monkeypatch.setattr(tasks, "_execute_register_source_library_scrapy_binding", Mock(return_value={}))

    def immediate_worker(**kwargs):
        tasks.task_orchestrate_crawler_deploy.run(**kwargs)
        return SimpleNamespace(id="fast-worker")

    response, _ = _submit_deploy(monkeypatch, callback=immediate_worker)
    assert response["run"]["status"] == "succeeded"
    assert response["run"]["external_job_id"] == "fast-worker"
    assert response["project"]["deployed_version"] == "v3"


def test_unbound_actions_reject_without_dispatch_or_mutation(crawler_store, monkeypatch):
    get_tasks = Mock()
    monkeypatch.setattr(service, "_tasks_module", get_tasks)
    with pytest.raises(ValueError, match="async_mode=true"):
        service.deploy_project(project_key="crawler_demo")
    for async_mode in (False, True):
        with pytest.raises(ValueError, match="no executor can confirm activation"):
            service.rollback_project(project_key="crawler_demo", target_version="v1", async_mode=async_mode)
    service.import_project({"project_key": "crawler_demo", "provider": "native", "version": "v3"})
    with pytest.raises(ValueError, match="No crawler deployment executor is bound for provider: native"):
        service.deploy_project(project_key="crawler_demo", async_mode=True)
    _assert_versions("v2", "v1")
    get_tasks.assert_not_called()
    assert service.list_deploy_runs(project_key="crawler_demo") == []


def test_legacy_rollback_worker_fails_without_remote_or_local_effects(monkeypatch):
    finalize = Mock()
    delete_version = Mock()
    toggle_provider = Mock()
    monkeypatch.setattr("app.services.crawlers_mgmt.finalize_deploy_run", finalize)
    monkeypatch.setattr(tasks, "_execute_crawler_rollback_version", delete_version)
    monkeypatch.setattr(tasks, "_execute_disable_source_library_channel_provider_native", toggle_provider)

    with pytest.raises(ValueError, match="no executor can confirm activation"):
        tasks.task_orchestrate_crawler_rollback.run(
            project_key="demo_proj", scrapy_project="crawler_demo", channel_key="crawler.demo",
            deploy_run_id=71, version="v1",
        )

    finalize.assert_called_once()
    assert finalize.call_args.args == (71,)
    assert finalize.call_args.kwargs["status"] == "failed"
    delete_version.assert_not_called()
    toggle_provider.assert_not_called()
