from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient

    from app.api import project_customization as customization_api
    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.project_customization.interfaces import WorkflowDefinition, WorkflowStep

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


@pytest.fixture(scope="module")
def client():
    if _IMPORT_ERROR is not None:
        pytest.skip(f"project customization core contract tests require backend dependencies: {_IMPORT_ERROR}")
    return TestClient(backend_app)


def _fake_customization(project_key: str = "demo_proj"):
    return SimpleNamespace(
        project_key=project_key,
        get_workflow_mapping=lambda: {},
    )


class _AuthenticatedActorStateApp:
    def __init__(self, app, *, actor_id: str):
        self._app = app
        self._actor_id = actor_id

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            state = scope.setdefault("state", {})
            actor = {
                "actor_id": self._actor_id,
                "source": "test_authenticated_actor_context",
                "auth_type": "codex_test",
            }
            state["authenticated_actor"] = actor
            state["authenticated_actor_id"] = self._actor_id
            state["codex_authenticated_actor"] = actor
        await self._app(scope, receive, send)


def _authenticated_client(*, actor_id: str) -> TestClient:
    return TestClient(_AuthenticatedActorStateApp(backend_app, actor_id=actor_id))


def _assert_actor_audit(
    audit: dict,
    *,
    actor_id: str,
    identity_source: str,
    actor_trusted: bool | None = None,
    legacy_actor_id: str | None = None,
) -> None:
    assert audit["actor"] == actor_id
    assert audit["requested_by"] == actor_id
    assert audit["applied_by"] == actor_id
    assert audit["identity_source"] == identity_source
    if actor_trusted is not None:
        assert audit["actor_trusted"] is actor_trusted
    if legacy_actor_id is not None:
        assert audit["legacy_actor_id"] == legacy_actor_id


_WORKFLOW_GOVERNANCE_KEYS = {
    "contract_version",
    "object_type",
    "object_id",
    "project_key",
    "operation",
    "stage",
    "dry_run",
    "will_mutate",
    "requires_publish",
    "version",
    "operator",
    "target",
    "snapshot",
    "history",
    "reason",
    "compatible_object_types",
    "schema",
}


def _assert_workflow_governance_shape(
    governance: dict,
    *,
    operation: str,
    dry_run: bool,
    will_mutate: bool,
    object_id: str = "demo_proj:demo",
) -> None:
    assert set(governance) == _WORKFLOW_GOVERNANCE_KEYS
    assert governance["contract_version"] == "cross_object.publish_governance.v1"
    assert governance["object_type"] == "workflow_template"
    assert governance["object_id"] == object_id
    assert governance["operation"] == operation
    assert governance["dry_run"] is dry_run
    assert governance["will_mutate"] is will_mutate
    assert set(["dashboard", "report", "project"]).issubset(set(governance["compatible_object_types"]))
    assert governance["schema"]["object_type_field"] == "object_type"
    assert governance["schema"]["object_id_field"] == "object_id"


def _assert_workflow_dry_run_stable_fields(
    data: dict,
    *,
    version: int,
    readiness: str,
    steps_by_status: dict[str, int],
) -> None:
    assert data["dry_run"] is True
    assert data["config_version"] == version
    assert data["current_version"] == version
    assert data["governance"]["operation"] == "dry_run"
    assert data["governance"]["will_mutate"] is False
    assert data["impact_summary"]["writes_blocked"] is True
    assert data["impact_summary"]["runtime_tasks_blocked"] is True
    assert data["readiness"] == readiness
    assert data["steps_by_status"] == steps_by_status
    assert isinstance(data["quick_actions"], list)
    assert data["quick_actions"]


def test_get_workflow_template_missing_name_returns_invalid_input_envelope(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(customization_api, "get_project_customization", lambda project_key=None: _fake_customization())

    response = client.get("/api/v1/project-customization/workflows/%20%20/template")

    assert response.status_code == 400
    assert response.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert payload["detail"]["error"]["details"]["field"] == "workflow_name"


def test_get_workflow_template_missing_workflow_returns_not_found_envelope(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(customization_api, "get_project_customization", lambda project_key=None: _fake_customization())

    response = client.get("/api/v1/project-customization/workflows/demo/template")

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert payload["detail"]["error"]["details"]["workflow_name"] == "demo"


def test_upsert_workflow_template_requires_project_key_and_valid_steps(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(customization_api, "get_project_customization", lambda project_key=None: _fake_customization(project_key=""))

    missing_key = client.post(
        "/api/v1/project-customization/workflows/demo/template",
        json={"project_key": "", "steps": [{"handler": "ingest.market"}], "board_layout": {}},
    )
    invalid_steps = client.post(
        "/api/v1/project-customization/workflows/demo/template",
        json={"project_key": "demo_proj", "steps": [{"handler": " "}], "board_layout": {}},
    )

    assert missing_key.status_code == 400
    assert missing_key.headers.get("x-error-code") == ErrorCode.PROJECT_KEY_REQUIRED.value
    assert missing_key.json()["detail"]["error"]["code"] == ErrorCode.PROJECT_KEY_REQUIRED.value

    assert invalid_steps.status_code == 400
    assert invalid_steps.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    assert invalid_steps.json()["detail"]["error"]["details"]["field"] == "steps[1].handler"


def test_delete_workflow_template_missing_custom_workflow_returns_not_found_envelope(client):
    response = client.delete(
        "/api/v1/project-customization/workflows/demo/template",
        params={"project_key": "demo_proj"},
    )

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert payload["detail"]["error"]["details"]["workflow_name"] == "demo"


def test_run_workflow_errors_use_standard_envelope(client, monkeypatch: pytest.MonkeyPatch):
    def _boom(**_kwargs):
        raise ValueError("bad workflow input")

    monkeypatch.setattr(customization_api, "execute_project_workflow", _boom)

    missing_key = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        json={"project_key": "", "params": {}},
    )
    invalid_run = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        json={"project_key": "demo_proj", "params": {}},
    )

    assert missing_key.status_code == 400
    assert missing_key.headers.get("x-error-code") == ErrorCode.PROJECT_KEY_REQUIRED.value
    assert missing_key.json()["detail"]["error"]["code"] == ErrorCode.PROJECT_KEY_REQUIRED.value

    assert invalid_run.status_code == 400
    assert invalid_run.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    payload = invalid_run.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_run_workflow_not_found_error_uses_matching_status_code(client, monkeypatch: pytest.MonkeyPatch):
    def _missing(**_kwargs):
        raise RuntimeError("workflow not found")

    monkeypatch.setattr(customization_api, "execute_project_workflow", _missing)

    response = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        json={"project_key": "demo_proj", "params": {}},
    )

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value


def test_run_workflow_dry_run_returns_preview_without_execution(client, monkeypatch: pytest.MonkeyPatch):
    if _IMPORT_ERROR is not None:
        pytest.skip(f"project customization core contract tests require backend dependencies: {_IMPORT_ERROR}")

    workflow = WorkflowDefinition(
        steps=[
            WorkflowStep(handler="ingest.market", params={"limit": 1}, name="Collect market"),
            WorkflowStep(handler="custom.missing", params={}, name="Missing custom handler"),
            WorkflowStep(handler="ingest.google_news", enabled=False, name="Disabled news"),
        ]
    )
    calls: list[dict] = []
    writes: list[dict] = []

    monkeypatch.setattr(
        customization_api,
        "get_project_customization",
        lambda project_key=None: SimpleNamespace(
            project_key=project_key or "demo_proj",
            get_workflow_mapping=lambda: {"demo": workflow},
        ),
    )
    monkeypatch.setattr(customization_api, "load_custom_workflow_definition", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(customization_api, "load_custom_workflow_board_layout", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        customization_api,
        "get_config",
        lambda *_args, **_kwargs: {"payload": {"version": 7, "workflows": {}, "boards": {}}},
    )
    monkeypatch.setattr(customization_api, "upsert_config", lambda **kwargs: writes.append(kwargs))

    def _execute(**kwargs):
        calls.append(kwargs)
        raise AssertionError("dry-run must not execute workflow handlers")

    monkeypatch.setattr(customization_api, "execute_project_workflow", _execute)

    response = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        params={"dry_run": "true"},
        json={"project_key": "demo_proj", "params": {"limit": 2}},
    )

    assert response.status_code == 200
    assert calls == []
    assert writes == []
    payload = response.json()
    assert payload["status"] == "ok"
    data = payload["data"]
    _assert_workflow_governance_shape(
        data["governance"],
        operation="dry_run",
        dry_run=True,
        will_mutate=False,
    )
    assert data["governance"]["target"]["object_id"] == "demo_proj:demo"
    assert data["governance"]["version"] == {"current": 7, "next": 7, "target": 7}
    _assert_workflow_dry_run_stable_fields(
        data,
        version=7,
        readiness="blocked",
        steps_by_status={"ready": 1, "blocked": 1, "skipped": 1},
    )
    assert data["status"] == "blocked"
    assert data["reason_code"] == "missing_workflow_handler"
    assert data["risk_level"] == "high"
    assert data["readiness_summary"] == "Dry-run is blocked because one or more enabled workflow handlers are missing."
    assert data["affected_areas"] == ["workflow_handlers", "runtime_execution"]
    assert data["policy_change"]["changed"] is False
    assert data["policy_change"]["requires_publish"] is False
    assert data["user_action_required"] is True
    assert data["blocking_reasons"] == [
        {
            "kind": "workflow_handler",
            "message": "workflow handler not found: custom.missing",
            "step_index": 2,
            "handler": "custom.missing",
        }
    ]
    assert data["user_actions"] == [
        {
            "kind": "install_or_register_workflow_handler",
            "message": "Register workflow handler before execution: custom.missing",
            "step_index": 2,
            "handler": "custom.missing",
        }
    ]
    assert data["quick_actions"] == [
        {
            "kind": "install_or_register_workflow_handler",
            "message": "Register workflow handler before execution: custom.missing",
            "action_priority": "high",
            "reason_code": "missing_workflow_handler",
            "step_index": 2,
            "handler": "custom.missing",
        }
    ]
    assert data["missing_dependencies"] == [
        {
            "index": 2,
            "name": "Missing custom handler",
            "handler": "custom.missing",
            "kind": "workflow_handler",
            "message": "workflow handler not found: custom.missing",
        }
    ]
    assert data["impact_summary"]["will_execute"] is False
    assert data["impact_summary"]["writes_blocked"] is True
    assert data["impact_summary"]["steps_total"] == 3
    assert data["impact_summary"]["reason_code"] == "missing_workflow_handler"
    assert data["impact_summary"]["risk_level"] == "high"
    assert data["impact_summary"]["readiness"] == "blocked"
    assert data["impact_summary"]["affected_areas"] == ["workflow_handlers", "runtime_execution"]
    assert data["impact_summary"]["policy_change"]["stage"] == "dry_run"
    assert data["impact_summary"]["blocking_reason_count"] == 1
    assert data["impact_summary"]["user_action_required"] is True
    assert data["impact_summary"]["quick_actions_count"] == 1
    assert data["steps"][0]["risk_level"] == "low"
    assert data["steps"][0]["readiness"] == "ready"
    assert data["steps"][1]["risk_level"] == "high"
    assert data["steps"][1]["readiness"] == "blocked"
    assert data["steps"][2]["risk_level"] == "low"
    assert data["steps"][2]["readiness"] == "skipped"


def test_run_workflow_dry_run_reports_ready_low_risk_when_dependencies_exist(
    client, monkeypatch: pytest.MonkeyPatch
):
    if _IMPORT_ERROR is not None:
        pytest.skip(f"project customization core contract tests require backend dependencies: {_IMPORT_ERROR}")

    workflow = WorkflowDefinition(
        steps=[
            WorkflowStep(handler="ingest.market", params={"limit": 1}, name="Collect market"),
            WorkflowStep(handler="ingest.google_news", enabled=False, name="Disabled news"),
        ]
    )
    calls: list[dict] = []
    writes: list[dict] = []

    monkeypatch.setattr(
        customization_api,
        "get_project_customization",
        lambda project_key=None: SimpleNamespace(
            project_key=project_key or "demo_proj",
            get_workflow_mapping=lambda: {"demo": workflow},
        ),
    )
    monkeypatch.setattr(customization_api, "load_custom_workflow_definition", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(customization_api, "load_custom_workflow_board_layout", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        customization_api,
        "get_config",
        lambda *_args, **_kwargs: {"payload": {"version": 8, "workflows": {}, "boards": {}}},
    )
    monkeypatch.setattr(customization_api, "upsert_config", lambda **kwargs: writes.append(kwargs))

    def _execute(**kwargs):
        calls.append(kwargs)
        raise AssertionError("dry-run must not execute workflow handlers")

    monkeypatch.setattr(customization_api, "execute_project_workflow", _execute)

    response = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        params={"dry_run": "true"},
        json={"project_key": "demo_proj", "params": {"limit": 2}},
    )

    assert response.status_code == 200
    assert calls == []
    assert writes == []
    payload = response.json()
    assert payload["status"] == "ok"
    data = payload["data"]
    _assert_workflow_governance_shape(
        data["governance"],
        operation="dry_run",
        dry_run=True,
        will_mutate=False,
    )
    assert data["governance"]["version"] == {"current": 8, "next": 8, "target": 8}
    _assert_workflow_dry_run_stable_fields(
        data,
        version=8,
        readiness="ready",
        steps_by_status={"ready": 1, "blocked": 0, "skipped": 1},
    )
    assert data["status"] == "ok"
    assert data["reason_code"] == "workflow_ready"
    assert data["risk_level"] == "low"
    assert data["affected_areas"] == ["runtime_execution"]
    assert data["readiness_summary"] == "Dry-run found all enabled workflow handlers; workflow is ready to execute."
    assert data["missing_dependencies"] == []
    assert data["blocking_reasons"] == []
    assert data["user_action_required"] is False
    assert data["user_actions"] == []
    assert data["quick_actions"][0]["kind"] == "execute_workflow"
    assert data["quick_actions"][0]["action_priority"] == "low"
    assert data["impact_summary"]["risk_level"] == "low"
    assert data["impact_summary"]["reason_code"] == "workflow_ready"
    assert data["impact_summary"]["policy_change"]["requires_publish"] is False
    assert data["impact_summary"]["readiness"] == "ready"
    assert data["impact_summary"]["blocking_reason_count"] == 0
    assert data["impact_summary"]["user_action_required"] is False


def test_workflow_template_diff_returns_versioned_preview_without_mutation(client, monkeypatch: pytest.MonkeyPatch):
    workflow = WorkflowDefinition(
        steps=[
            WorkflowStep(handler="ingest.market", params={"limit": 1}, name="Collect market"),
            WorkflowStep(handler="ingest.google_news", params={"q": "chips"}, name="News"),
        ]
    )
    writes: list[dict] = []

    monkeypatch.setattr(
        customization_api,
        "get_project_customization",
        lambda project_key=None: SimpleNamespace(
            project_key=project_key or "demo_proj",
            get_workflow_mapping=lambda: {"demo": workflow},
        ),
    )
    monkeypatch.setattr(customization_api, "load_custom_workflow_definition", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(customization_api, "load_custom_workflow_board_layout", lambda *_args, **_kwargs: {"layout": "trend"})
    monkeypatch.setattr(
        customization_api,
        "get_config",
        lambda *_args, **_kwargs: {"payload": {"version": 9, "workflows": {}, "boards": {}}},
    )
    monkeypatch.setattr(customization_api, "upsert_config", lambda **kwargs: writes.append(kwargs))

    response = client.post(
        "/api/v1/project-customization/workflows/demo/template/diff",
        json={
            "project_key": "demo_proj",
            "steps": [
                {"handler": "ingest.market", "params": {"limit": 2}, "enabled": True, "name": "Collect market"},
                {"handler": "ingest.reddit", "params": {"q": "chips"}, "enabled": True, "name": "Reddit"},
            ],
            "board_layout": {"layout": "table"},
        },
    )

    assert response.status_code == 200
    assert writes == []
    payload = response.json()
    assert payload["status"] == "ok"
    data = payload["data"]
    _assert_workflow_governance_shape(
        data["governance"],
        operation="snapshot",
        dry_run=True,
        will_mutate=False,
    )
    assert data["governance"]["requires_publish"] is True
    assert data["project_key"] == "demo_proj"
    assert data["workflow_name"] == "demo"
    assert data["changed"] is True
    assert data["reason_code"] == "workflow_template_steps_and_board_changed"
    assert data["risk_level"] == "medium"
    assert data["affected_areas"] == ["workflow_steps", "graph_board_layout", "publish_policy"]
    assert data["current_version"] == 9
    assert data["next_version"] == 10
    assert data["policy_change"]["changed"] is True
    assert data["policy_change"]["requires_publish"] is True
    assert data["impact_summary"]["reason_code"] == "workflow_template_steps_and_board_changed"
    assert data["impact_summary"]["risk_level"] == "medium"
    assert data["impact_summary"]["steps_changed"] == 2
    assert data["quick_actions"][0]["kind"] == "publish_workflow_template"
    assert data["version_summary"] == {
        "active_version": 9,
        "draft_version": 10,
        "staging_version": None,
        "stage": "draft_preview",
        "source": "builtin",
        "will_mutate": False,
        "requires_publish": True,
    }
    assert data["diff"]["step_count_before"] == 2
    assert data["diff"]["step_count_after"] == 2
    assert data["diff"]["board_layout_changed"] is True
    assert [item["change_type"] for item in data["diff"]["steps"]] == ["modified", "modified"]
    assert data["diff"]["steps"][0]["before"]["params"] == {"limit": 1}
    assert data["diff"]["steps"][0]["after"]["params"] == {"limit": 2}


def test_workflow_template_diff_requires_explicit_project_key(client):
    response = client.post(
        "/api/v1/project-customization/workflows/demo/template/diff",
        json={"project_key": "", "steps": [{"handler": "ingest.market"}], "board_layout": {}},
    )

    assert response.status_code == 400
    assert response.headers.get("x-error-code") == ErrorCode.PROJECT_KEY_REQUIRED.value
    assert response.json()["detail"]["error"]["code"] == ErrorCode.PROJECT_KEY_REQUIRED.value


def test_workflow_template_stage_save_and_promote_preserves_active_until_publish(client, monkeypatch: pytest.MonkeyPatch):
    config_state = {"payload": {"version": 4, "workflows": {}, "boards": {}, "workflow_stages": {}}}
    writes: list[dict] = []

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)

    def _upsert_config(**kwargs):
        write = {**kwargs, "payload": deepcopy(kwargs["payload"])}
        writes.append(write)
        config_state["payload"] = deepcopy(kwargs["payload"])
        return {"project_key": kwargs["project_key"], "payload": kwargs["payload"]}

    monkeypatch.setattr(customization_api, "upsert_config", _upsert_config)

    draft = client.post(
        "/api/v1/project-customization/workflows/demo/template/stage",
        json={
            "project_key": "demo_proj",
            "stage": "draft",
            "actor": "planner",
            "trace_id": "trace-draft-1",
            "steps": [{"handler": "ingest.market", "params": {"limit": 2}, "name": "Collect"}],
            "board_layout": {"layout": "table"},
        },
    )
    versions_after_draft = client.get(
        "/api/v1/project-customization/workflows/demo/template/versions",
        params={"project_key": "demo_proj"},
    )
    staging = client.post(
        "/api/v1/project-customization/workflows/demo/template/promote",
        json={
            "project_key": "demo_proj",
            "from_stage": "draft",
            "to_stage": "staging",
            "requested_by": "reviewer",
            "trace_id": "trace-promote-staging",
        },
    )
    active = client.post(
        "/api/v1/project-customization/workflows/demo/template/promote",
        json={
            "project_key": "demo_proj",
            "from_stage": "staging",
            "to_stage": "active",
            "actor": "publisher",
            "trace_id": "trace-promote-active",
        },
    )

    assert draft.status_code == 200
    draft_data = draft.json()["data"]
    assert draft_data["stage"] == "draft"
    _assert_workflow_governance_shape(
        draft_data["governance"],
        operation="stage",
        dry_run=False,
        will_mutate=True,
    )
    assert draft_data["governance"]["requires_publish"] is True
    assert draft_data["governance"]["snapshot"]["stage"] == "draft"
    assert draft_data["current_version"] == 4
    assert draft_data["next_version"] == 5
    assert draft_data["audit"]["actor"] == "planner"
    assert draft_data["audit"]["identity_source"] == "payload"
    assert draft_data["audit"]["action"] == "save_stage"
    assert draft_data["audit"]["from_stage"] is None
    assert draft_data["audit"]["to_stage"] == "draft"
    assert draft_data["audit"]["version"] == 5
    assert draft_data["audit"]["trace_id"] == "trace-draft-1"
    assert draft_data["stage_record"]["audit"]["created_at"]
    assert draft_data["version_summary"]["requires_publish"] is True
    assert "demo" not in writes[0]["payload"]["workflows"]
    assert writes[0]["payload"]["workflow_stage_history"]["demo"][0]["stage_snapshot"]["stage"] == "draft"

    assert versions_after_draft.status_code == 200
    versions_data = versions_after_draft.json()["data"]
    _assert_workflow_governance_shape(
        versions_data["governance"],
        operation="history",
        dry_run=True,
        will_mutate=False,
    )
    assert versions_data["governance"]["history"]["count"] == 1
    assert versions_data["stage_summary"]["has_draft"] is True
    assert versions_data["stage_summary"]["has_active"] is False
    assert versions_data["stage_summary"]["latest_audit"]["trace_id"] == "trace-draft-1"
    assert versions_data["items"][0]["stage"] == "draft"
    assert versions_data["items"][0]["audit"]["requested_by"] == "planner"
    assert versions_data["history"][0]["action"] == "save_stage"
    assert "stage_snapshot" not in versions_data["history"][0]

    assert staging.status_code == 200
    staging_data = staging.json()["data"]
    assert staging_data["from_stage"] == "draft"
    assert staging_data["to_stage"] == "staging"
    assert staging_data["audit"]["actor"] == "reviewer"
    assert staging_data["audit"]["requested_by"] == "reviewer"
    assert staging_data["audit"]["applied_by"] == "reviewer"
    assert staging_data["audit"]["identity_source"] == "payload"
    assert staging_data["audit"]["action"] == "promote_stage"
    assert staging_data["audit"]["version"] == 6
    assert staging_data["history"][-1]["trace_id"] == "trace-promote-staging"
    assert staging_data["version_summary"]["requires_publish"] is True
    assert "demo" not in writes[1]["payload"]["workflows"]

    assert active.status_code == 200
    active_data = active.json()["data"]
    _assert_workflow_governance_shape(
        active_data["governance"],
        operation="publish",
        dry_run=False,
        will_mutate=True,
    )
    assert active_data["governance"]["requires_publish"] is False
    assert active_data["to_stage"] == "active"
    assert active_data["audit"]["actor"] == "publisher"
    assert active_data["audit"]["identity_source"] == "payload"
    assert active_data["audit"]["from_stage"] == "staging"
    assert active_data["audit"]["to_stage"] == "active"
    assert active_data["stage_record"]["promoted_from"] == "staging"
    assert active_data["version_summary"]["requires_publish"] is False
    assert config_state["payload"]["workflows"]["demo"]["steps"][0]["handler"] == "ingest.market"
    assert config_state["payload"]["boards"]["demo"]["layout"] == "table"
    assert len(config_state["payload"]["workflow_stage_history"]["demo"]) == 3
    assert len(writes) == 3


def test_workflow_template_stage_promote_and_rollback_prefer_authenticated_actor_context_over_spoofed_headers(
    monkeypatch: pytest.MonkeyPatch,
):
    config_state = {"payload": {"version": 1, "workflows": {}, "boards": {}, "workflow_stages": {}}}

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)

    def _upsert_config(**kwargs):
        config_state["payload"] = deepcopy(kwargs["payload"])
        return {"project_key": kwargs["project_key"], "payload": kwargs["payload"]}

    monkeypatch.setattr(customization_api, "upsert_config", _upsert_config)

    with _authenticated_client(actor_id="auth-stage-actor") as auth_client:
        draft = auth_client.post(
            "/api/v1/project-customization/workflows/demo/template/stage",
            headers={"X-Actor-Id": "spoofed-stage-header"},
            json={
                "project_key": "demo_proj",
                "stage": "draft",
                "steps": [{"handler": "ingest.market", "params": {"limit": 2}}],
                "board_layout": {"layout": "draft"},
            },
        )
    with _authenticated_client(actor_id="auth-promote-actor") as auth_client:
        staging = auth_client.post(
            "/api/v1/project-customization/workflows/demo/template/promote",
            headers={"X-User-Email": "spoofed-promoter@example.com"},
            json={
                "project_key": "demo_proj",
                "from_stage": "draft",
                "to_stage": "staging",
            },
        )
    with _authenticated_client(actor_id="auth-preview-actor") as auth_client:
        preview = auth_client.post(
            "/api/v1/project-customization/workflows/demo/template/rollback/preview",
            headers={"X-Request-Actor": "spoofed-preview-actor"},
            json={
                "project_key": "demo_proj",
                "target_stage": "staging",
                "target_version": 3,
            },
        )
    with _authenticated_client(actor_id="auth-rollback-actor") as auth_client:
        rollback = auth_client.post(
            "/api/v1/project-customization/workflows/demo/template/rollback",
            headers={"X-User-Id": "spoofed-rollback-user"},
            json={
                "project_key": "demo_proj",
                "target_stage": "staging",
                "target_version": 3,
            },
        )

    assert draft.status_code == 200
    _assert_actor_audit(
        draft.json()["data"]["audit"],
        actor_id="auth-stage-actor",
        identity_source="test_authenticated_actor_context",
        actor_trusted=True,
        legacy_actor_id="spoofed-stage-header",
    )

    assert staging.status_code == 200
    _assert_actor_audit(
        staging.json()["data"]["audit"],
        actor_id="auth-promote-actor",
        identity_source="test_authenticated_actor_context",
        actor_trusted=True,
        legacy_actor_id="spoofed-promoter@example.com",
    )

    assert preview.status_code == 200
    _assert_actor_audit(
        preview.json()["data"]["audit"],
        actor_id="auth-preview-actor",
        identity_source="test_authenticated_actor_context",
        actor_trusted=True,
        legacy_actor_id="spoofed-preview-actor",
    )
    assert preview.json()["data"]["rollback_plan"]["will_mutate"] is False

    assert rollback.status_code == 200
    _assert_actor_audit(
        rollback.json()["data"]["audit"],
        actor_id="auth-rollback-actor",
        identity_source="test_authenticated_actor_context",
        actor_trusted=True,
        legacy_actor_id="spoofed-rollback-user",
    )
    assert rollback.json()["data"]["rollback_applied"] is True


def test_workflow_template_stage_promote_payload_identity_wins_over_authenticated_context_and_headers(
    monkeypatch: pytest.MonkeyPatch,
):
    config_state = {"payload": {"version": 1, "workflows": {}, "boards": {}, "workflow_stages": {}}}

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)

    def _upsert_config(**kwargs):
        config_state["payload"] = deepcopy(kwargs["payload"])
        return {"project_key": kwargs["project_key"], "payload": kwargs["payload"]}

    monkeypatch.setattr(customization_api, "upsert_config", _upsert_config)

    with _authenticated_client(actor_id="auth-context-actor") as auth_client:
        draft = auth_client.post(
            "/api/v1/project-customization/workflows/demo/template/stage",
            headers={"X-Actor-Id": "spoofed-stage-header"},
            json={
                "project_key": "demo_proj",
                "stage": "draft",
                "actor": "payload-stage-actor",
                "steps": [{"handler": "ingest.market", "params": {"limit": 2}}],
                "board_layout": {"layout": "draft"},
            },
        )
        staging = auth_client.post(
            "/api/v1/project-customization/workflows/demo/template/promote",
            headers={"X-User-Email": "spoofed-promoter@example.com"},
            json={
                "project_key": "demo_proj",
                "from_stage": "draft",
                "to_stage": "staging",
                "requested_by": "payload-promoter",
            },
        )

    assert draft.status_code == 200
    draft_audit = draft.json()["data"]["audit"]
    assert draft_audit["actor"] == "payload-stage-actor"
    assert draft_audit["requested_by"] == "payload-stage-actor"
    assert draft_audit["applied_by"] == "payload-stage-actor"
    assert draft_audit["identity_source"] == "payload"

    assert staging.status_code == 200
    staging_audit = staging.json()["data"]["audit"]
    assert staging_audit["actor"] == "payload-promoter"
    assert staging_audit["requested_by"] == "payload-promoter"
    assert staging_audit["applied_by"] == "payload-promoter"
    assert staging_audit["identity_source"] == "payload"


def test_workflow_template_stage_promote_and_rollback_use_header_identity_when_payload_actor_missing(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    config_state = {"payload": {"version": 1, "workflows": {}, "boards": {}, "workflow_stages": {}}}

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)

    def _upsert_config(**kwargs):
        config_state["payload"] = deepcopy(kwargs["payload"])
        return {"project_key": kwargs["project_key"], "payload": kwargs["payload"]}

    monkeypatch.setattr(customization_api, "upsert_config", _upsert_config)

    draft = client.post(
        "/api/v1/project-customization/workflows/demo/template/stage",
        headers={"X-Actor-Id": "header-planner"},
        json={
            "project_key": "demo_proj",
            "stage": "draft",
            "steps": [{"handler": "ingest.market", "params": {"limit": 2}}],
            "board_layout": {"layout": "draft"},
        },
    )
    staging = client.post(
        "/api/v1/project-customization/workflows/demo/template/promote",
        headers={"X-User-Email": "reviewer@example.com"},
        json={
            "project_key": "demo_proj",
            "from_stage": "draft",
            "to_stage": "staging",
        },
    )
    preview = client.post(
        "/api/v1/project-customization/workflows/demo/template/rollback/preview",
        headers={"X-Request-Actor": "ops-preview"},
        json={
            "project_key": "demo_proj",
            "target_stage": "staging",
            "target_version": 3,
        },
    )
    rollback = client.post(
        "/api/v1/project-customization/workflows/demo/template/rollback",
        headers={"X-User-Id": "ops-user"},
        json={
            "project_key": "demo_proj",
            "target_stage": "staging",
            "target_version": 3,
        },
    )

    assert draft.status_code == 200
    draft_audit = draft.json()["data"]["audit"]
    _assert_actor_audit(
        draft_audit,
        actor_id="header-planner",
        identity_source="legacy_header",
        actor_trusted=False,
        legacy_actor_id="header-planner",
    )

    assert staging.status_code == 200
    staging_audit = staging.json()["data"]["audit"]
    _assert_actor_audit(
        staging_audit,
        actor_id="reviewer@example.com",
        identity_source="legacy_header",
        actor_trusted=False,
        legacy_actor_id="reviewer@example.com",
    )

    assert preview.status_code == 200
    preview_audit = preview.json()["data"]["audit"]
    _assert_actor_audit(
        preview_audit,
        actor_id="ops-preview",
        identity_source="legacy_header",
        actor_trusted=False,
        legacy_actor_id="ops-preview",
    )
    assert preview.json()["data"]["rollback_plan"]["will_mutate"] is False

    assert rollback.status_code == 200
    rollback_audit = rollback.json()["data"]["audit"]
    _assert_actor_audit(
        rollback_audit,
        actor_id="ops-user",
        identity_source="legacy_header",
        actor_trusted=False,
        legacy_actor_id="ops-user",
    )
    assert rollback.json()["data"]["rollback_applied"] is True


def test_workflow_template_stage_uses_system_identity_when_payload_and_headers_missing(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    config_state = {"payload": {"version": 4, "workflows": {}, "boards": {}, "workflow_stages": {}}}

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)
    monkeypatch.setattr(
        customization_api,
        "upsert_config",
        lambda **kwargs: {"project_key": kwargs["project_key"], "payload": kwargs["payload"]},
    )

    response = client.post(
        "/api/v1/project-customization/workflows/demo/template/stage",
        json={
            "project_key": "demo_proj",
            "stage": "draft",
            "steps": [{"handler": "ingest.market", "params": {"limit": 1}}],
        },
    )

    assert response.status_code == 200
    audit = response.json()["data"]["audit"]
    assert audit["actor"] == "system"
    assert audit["requested_by"] == "system"
    assert audit["applied_by"] == "system"
    assert audit["identity_source"] == "system"


def test_workflow_template_rollback_preview_returns_audited_plan_without_mutation(client, monkeypatch: pytest.MonkeyPatch):
    config_state = {
        "payload": {
            "version": 7,
            "workflows": {"demo": {"steps": [{"handler": "ingest.market", "params": {"limit": 5}}]}},
            "boards": {"demo": {"layout": "active"}},
            "workflow_stages": {
                "demo": {
                    "staging": {
                        "stage": "staging",
                        "version": 6,
                        "steps": [{"handler": "ingest.market", "params": {"limit": 2}}],
                        "board_layout": {"layout": "staging"},
                        "requires_publish": True,
                    },
                    "active": {
                        "stage": "active",
                        "version": 7,
                        "steps": [{"handler": "ingest.market", "params": {"limit": 5}}],
                        "board_layout": {"layout": "active"},
                        "requires_publish": False,
                    },
                }
            },
            "workflow_stage_history": {
                "demo": [
                    {
                        "actor": "reviewer",
                        "requested_by": "reviewer",
                        "applied_by": "reviewer",
                        "action": "promote_stage",
                        "from_stage": "draft",
                        "to_stage": "staging",
                        "version": 6,
                        "created_at": "2026-05-24T00:00:00Z",
                        "trace_id": "trace-staging",
                        "stage_snapshot": {
                            "stage": "staging",
                            "version": 6,
                            "steps": [{"handler": "ingest.market", "params": {"limit": 2}}],
                            "board_layout": {"layout": "staging"},
                            "requires_publish": True,
                        },
                    }
                ]
            },
        }
    }
    writes: list[dict] = []

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)
    monkeypatch.setattr(customization_api, "upsert_config", lambda **kwargs: writes.append(kwargs))

    response = client.post(
        "/api/v1/project-customization/workflows/demo/template/rollback/preview",
        json={
            "project_key": "demo_proj",
            "target_stage": "staging",
            "target_version": 6,
            "requested_by": "ops",
            "trace_id": "trace-rollback-preview",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rollback_preview"] is True
    _assert_workflow_governance_shape(
        data["governance"],
        operation="rollback",
        dry_run=True,
        will_mutate=False,
    )
    assert data["governance"]["target"]["stage"] == "staging"
    assert data["governance"]["target"]["version"] == 6
    assert data["governance"]["snapshot"]["version"] == 6
    assert data["governance"]["operator"]["actor"] == "ops"
    assert data["governance"]["reason"] == "rollback preview requested"
    assert data["current_version"] == 7
    assert data["next_version"] == 8
    assert data["audit"]["actor"] == "ops"
    assert data["audit"]["action"] == "rollback_preview"
    assert data["audit"]["from_stage"] == "active"
    assert data["audit"]["to_stage"] == "staging"
    assert data["audit"]["trace_id"] == "trace-rollback-preview"
    assert data["rollback_plan"]["mode"] == "preview_only"
    assert data["rollback_plan"]["can_execute"] is True
    assert data["rollback_plan"]["will_mutate"] is False
    assert data["rollback_plan"]["target_version"] == 6
    assert data["rollback_plan"]["target_stage_record"]["board_layout"]["layout"] == "staging"
    assert data["version_summary"]["stage"] == "rollback_preview"
    assert data["version_summary"]["will_mutate"] is False
    assert data["history"][0]["trace_id"] == "trace-staging"
    assert "stage_snapshot" not in data["history"][0]
    assert writes == []


def test_workflow_template_rollback_apply_restores_active_snapshot_and_persists(client, monkeypatch: pytest.MonkeyPatch):
    config_state = {
        "payload": {
            "version": 9,
            "workflows": {"demo": {"steps": [{"handler": "ingest.market", "params": {"limit": 9}}]}},
            "boards": {"demo": {"layout": "active-v9"}},
            "workflow_stages": {
                "demo": {
                    "active": {
                        "stage": "active",
                        "version": 9,
                        "steps": [{"handler": "ingest.market", "params": {"limit": 9}}],
                        "board_layout": {"layout": "active-v9"},
                        "requires_publish": False,
                    },
                }
            },
            "workflow_stage_history": {
                "demo": [
                    {
                        "actor": "publisher",
                        "requested_by": "publisher",
                        "applied_by": "publisher",
                        "action": "promote_stage",
                        "from_stage": "staging",
                        "to_stage": "active",
                        "version": 7,
                        "created_at": "2026-05-24T00:00:00Z",
                        "trace_id": "trace-active-v7",
                        "stage_snapshot": {
                            "stage": "active",
                            "version": 7,
                            "steps": [{"handler": "ingest.market", "params": {"limit": 3}}],
                            "board_layout": {"layout": "active-v7"},
                            "requires_publish": False,
                        },
                    }
                ]
            },
        }
    }
    writes: list[dict] = []

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)

    def _upsert_config(**kwargs):
        write = {**kwargs, "payload": deepcopy(kwargs["payload"])}
        writes.append(write)
        config_state["payload"] = deepcopy(kwargs["payload"])
        return {"project_key": kwargs["project_key"], "payload": kwargs["payload"]}

    monkeypatch.setattr(customization_api, "upsert_config", _upsert_config)

    response = client.post(
        "/api/v1/project-customization/workflows/demo/template/rollback",
        json={
            "project_key": "demo_proj",
            "target_stage": "active",
            "target_version": 7,
            "requested_by": "ops",
            "trace_id": "trace-rollback-apply-active",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rollback_applied"] is True
    _assert_workflow_governance_shape(
        data["governance"],
        operation="rollback",
        dry_run=False,
        will_mutate=True,
    )
    assert data["governance"]["target"]["stage"] == "active"
    assert data["governance"]["target"]["version"] == 7
    assert data["governance"]["snapshot"]["version"] == 7
    assert data["governance"]["operator"]["actor"] == "ops"
    assert data["governance"]["reason"] == "rollback applied"
    assert data["current_version"] == 9
    assert data["next_version"] == 10
    assert data["audit"]["actor"] == "ops"
    assert data["audit"]["requested_by"] == "ops"
    assert data["audit"]["applied_by"] == "ops"
    assert data["audit"]["action"] == "rollback_apply"
    assert data["audit"]["from_stage"] == "active"
    assert data["audit"]["to_stage"] == "active"
    assert data["audit"]["from_version"] == 9
    assert data["audit"]["to_version"] == 10
    assert data["audit"]["target_version"] == 7
    assert data["audit"]["trace_id"] == "trace-rollback-apply-active"
    assert data["audit"]["snapshot"]["version"] == 7
    assert data["audit"]["operator"]["actor"] == "ops"
    assert data["audit"]["target"]["version"] == 7
    assert data["audit"]["reason"] == "rollback applied"
    assert data["rollback_plan"]["mode"] == "apply"
    assert data["rollback_plan"]["will_mutate"] is True
    assert data["rollback_plan"]["target_version"] == 7
    assert data["rollback_plan"]["applied_stage_record"]["version"] == 10
    assert data["stage_record"]["steps"][0]["params"] == {"limit": 3}
    assert data["stage_record"]["board_layout"] == {"layout": "active-v7"}
    assert data["stage_record"]["requires_publish"] is False
    assert data["version_summary"]["requires_publish"] is False
    assert data["version_summary"]["active_version"] == 10
    assert data["history"][-1]["action"] == "rollback_apply"
    assert "stage_snapshot" not in data["history"][-1]
    assert len(writes) == 1
    written_payload = writes[0]["payload"]
    assert written_payload["version"] == 10
    assert written_payload["workflows"]["demo"]["steps"][0]["params"] == {"limit": 3}
    assert written_payload["boards"]["demo"] == {"layout": "active-v7"}
    assert written_payload["workflow_stages"]["demo"]["active"]["version"] == 10
    assert written_payload["workflow_stage_history"]["demo"][-1]["stage_snapshot"]["version"] == 10


def test_workflow_template_rollback_apply_restores_staging_without_publishing_active(client, monkeypatch: pytest.MonkeyPatch):
    config_state = {
        "payload": {
            "version": 12,
            "workflows": {"demo": {"steps": [{"handler": "ingest.market", "params": {"limit": 12}}]}},
            "boards": {"demo": {"layout": "active-v12"}},
            "workflow_stages": {
                "demo": {
                    "active": {
                        "stage": "active",
                        "version": 12,
                        "steps": [{"handler": "ingest.market", "params": {"limit": 12}}],
                        "board_layout": {"layout": "active-v12"},
                        "requires_publish": False,
                    },
                    "staging": {
                        "stage": "staging",
                        "version": 11,
                        "steps": [{"handler": "ingest.market", "params": {"limit": 11}}],
                        "board_layout": {"layout": "staging-v11"},
                        "requires_publish": True,
                    },
                }
            },
            "workflow_stage_history": {
                "demo": [
                    {
                        "actor": "reviewer",
                        "requested_by": "reviewer",
                        "applied_by": "reviewer",
                        "action": "promote_stage",
                        "from_stage": "draft",
                        "to_stage": "staging",
                        "version": 8,
                        "created_at": "2026-05-24T00:00:00Z",
                        "trace_id": "trace-staging-v8",
                        "stage_snapshot": {
                            "stage": "staging",
                            "version": 8,
                            "steps": [{"handler": "ingest.market", "params": {"limit": 8}}],
                            "board_layout": {"layout": "staging-v8"},
                            "requires_publish": True,
                        },
                    }
                ]
            },
        }
    }
    writes: list[dict] = []

    monkeypatch.setattr(customization_api, "get_config", lambda *_args, **_kwargs: config_state)

    def _upsert_config(**kwargs):
        write = {**kwargs, "payload": deepcopy(kwargs["payload"])}
        writes.append(write)
        config_state["payload"] = deepcopy(kwargs["payload"])
        return {"project_key": kwargs["project_key"], "payload": kwargs["payload"]}

    monkeypatch.setattr(customization_api, "upsert_config", _upsert_config)

    response = client.post(
        "/api/v1/project-customization/workflows/demo/template/rollback",
        json={
            "project_key": "demo_proj",
            "target_stage": "staging",
            "target_version": 8,
            "actor": "ops",
            "trace_id": "trace-rollback-apply-staging",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rollback_applied"] is True
    assert data["next_version"] == 13
    assert data["audit"]["action"] == "rollback_apply"
    assert data["audit"]["from_version"] == 11
    assert data["audit"]["to_version"] == 13
    assert data["audit"]["target_version"] == 8
    assert data["version_summary"]["requires_publish"] is True
    assert data["version_summary"]["active_version"] == 12
    assert data["version_summary"]["staging_version"] == 13
    assert data["stage_record"]["requires_publish"] is True
    assert len(writes) == 1
    written_payload = writes[0]["payload"]
    assert written_payload["workflows"]["demo"]["steps"][0]["params"] == {"limit": 12}
    assert written_payload["boards"]["demo"] == {"layout": "active-v12"}
    assert written_payload["workflow_stages"]["demo"]["staging"]["steps"][0]["params"] == {"limit": 8}
    assert written_payload["workflow_stages"]["demo"]["staging"]["board_layout"] == {"layout": "staging-v8"}


def test_workflow_template_promote_missing_stage_returns_not_found(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        customization_api,
        "get_config",
        lambda *_args, **_kwargs: {"payload": {"version": 1, "workflows": {}, "boards": {}, "workflow_stages": {}}},
    )

    response = client.post(
        "/api/v1/project-customization/workflows/demo/template/promote",
        json={"project_key": "demo_proj", "from_stage": "draft", "to_stage": "staging"},
    )

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    assert response.json()["detail"]["error"]["details"] == {"workflow_name": "demo", "stage": "draft"}
