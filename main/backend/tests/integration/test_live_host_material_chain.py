from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import select


pytestmark = pytest.mark.integration


_TERMINAL_TURN_STATES = {"completed", "failed", "interrupted"}


@dataclass(frozen=True)
class _LiveHostConfig:
    webui_url: str
    webui_api_key: str
    backend_url: str
    project_key: str
    model: str
    timeout_seconds: int


def _required_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        pytest.fail(f"{name} is required when MRW_LIVE_HOST_MATERIAL_CHAIN=1")
    return value


def _live_config() -> _LiveHostConfig:
    if os.getenv("MRW_LIVE_HOST_MATERIAL_CHAIN") != "1":
        pytest.skip("real Codex OAuth/model calls require MRW_LIVE_HOST_MATERIAL_CHAIN=1")
    return _LiveHostConfig(
        webui_url=_required_env("MRW_LIVE_HOST_WEBUI_URL").rstrip("/"),
        webui_api_key=_required_env("MRW_LIVE_HOST_WEBUI_API_KEY"),
        backend_url=_required_env("MRW_LIVE_HOST_BACKEND_URL").rstrip("/"),
        project_key=_required_env("MRW_LIVE_HOST_PROJECT_KEY"),
        model=str(os.getenv("MRW_LIVE_HOST_MODEL") or "gpt-6-luna").strip(),
        timeout_seconds=max(60, int(os.getenv("MRW_LIVE_HOST_TIMEOUT_SECONDS") or "300")),
    )


def _json_request(
    method: str,
    url: str,
    *,
    bearer: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    headers = {"Accept": "application/json"}
    payload = None
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(
            f"{method} {url} returned HTTP {exc.code}: {error_body[:2000]}"
        ) from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def _webui(
    config: _LiveHostConfig,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> Any:
    return _json_request(
        method,
        f"{config.webui_url}{path}",
        bearer=config.webui_api_key,
        body=body,
    )


def _find_turn(config: _LiveHostConfig, thread_id: str, turn_id: str) -> dict[str, Any] | None:
    try:
        page = _webui(
            config,
            "GET",
            f"/api/threads/{quote(thread_id, safe='')}/turns?limit=20&sortDirection=desc&itemsView=summary",
        )
    except AssertionError as exc:
        message = str(exc)
        startup_transient = (
            "rollout" in message and "is empty" in message
        ) or "list_turns is not supported yet" in message
        if "returned HTTP 502" in message and startup_transient:
            return None
        raise
    rows = page.get("data", []) if isinstance(page, dict) else []
    return next(
        (row for row in rows if isinstance(row, dict) and row.get("id") == turn_id),
        None,
    )


def _wait_for_approved_turn(
    config: _LiveHostConfig,
    *,
    thread_id: str,
    turn_id: str,
    title: str,
    marker: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + config.timeout_seconds
    approved_action: dict[str, Any] | None = None
    terminal_turn: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        pending = _webui(
            config,
            "GET",
            f"/api/mrw/pending?threadId={quote(thread_id, safe='')}",
        )
        if isinstance(pending, list) and pending:
            assert approved_action is None, "the bounded turn requested more than one write approval"
            assert len(pending) == 1, f"expected one pending action, received {len(pending)}"
            action = pending[0]
            assert action.get("threadId") == thread_id
            assert action.get("turnId") == turn_id
            assert action.get("toolName") == "writing.document.create"
            arguments = action.get("arguments") or {}
            assert arguments.get("title") == title
            assert marker in str(arguments.get("body_md") or "")
            assert arguments.get("dry_run") is not True
            _webui(
                config,
                "POST",
                "/api/mrw/confirm",
                body={
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "actionId": action["actionId"],
                    "approved": True,
                    "userText": "Approve this exact bounded live-host writing material creation.",
                },
            )
            approved_action = action

        turn = _find_turn(config, thread_id, turn_id)
        if turn is not None and str(turn.get("status") or "") in _TERMINAL_TURN_STATES:
            terminal_turn = turn
            break
        time.sleep(1)

    assert terminal_turn is not None, (
        "the real model turn did not reach a terminal state; "
        f"write_approval_observed={approved_action is not None}"
    )
    assert terminal_turn.get("status") == "completed", terminal_turn.get("error")
    assert approved_action is not None, "the real model never requested the registered write approval"
    return approved_action, terminal_turn


def _interrupt_nonterminal_turn(
    config: _LiveHostConfig,
    *,
    thread_id: str,
    turn_id: str,
) -> None:
    """Best-effort cleanup so a failed acceptance does not leave a live model turn."""

    try:
        turn = _find_turn(config, thread_id, turn_id)
    except Exception:
        turn = None
    if turn is not None and str(turn.get("status") or "") in _TERMINAL_TURN_STATES:
        return
    try:
        _webui(
            config,
            "POST",
            (
                f"/api/threads/{quote(thread_id, safe='')}/turns/"
                f"{quote(turn_id, safe='')}/interrupt"
            ),
        )
    except Exception:
        # Preserve the original acceptance failure; runtime logs retain cleanup diagnostics.
        return


def _backend_document(config: _LiveHostConfig, doc_id: int) -> dict[str, Any]:
    response = _json_request(
        "GET",
        (
            f"{config.backend_url}/api/v1/writing/documents/{doc_id}"
            f"?project_key={quote(config.project_key, safe='')}"
        ),
    )
    assert isinstance(response, dict) and response.get("status") == "ok", response
    document = response.get("data")
    assert isinstance(document, dict)
    return document


def _ensure_project(config: _LiveHostConfig) -> dict[str, Any]:
    """Use the product project owner to bootstrap an otherwise empty isolated stack."""

    response = _json_request("GET", f"{config.backend_url}/api/v1/projects")
    assert isinstance(response, dict) and response.get("status") == "ok", response
    data = response.get("data") or {}
    projects = data.get("items", []) if isinstance(data, dict) else []
    existing = next(
        (
            row
            for row in projects
            if isinstance(row, dict) and row.get("project_key") == config.project_key
        ),
        None,
    )
    if existing is None:
        created = _json_request(
            "POST",
            f"{config.backend_url}/api/v1/projects",
            body={
                "project_key": config.project_key,
                "name": "Live Host Material Chain",
                "enabled": True,
            },
        )
        assert isinstance(created, dict) and created.get("status") == "ok", created
        response = _json_request("GET", f"{config.backend_url}/api/v1/projects")
        data = response.get("data") or {}
        projects = data.get("items", []) if isinstance(data, dict) else []
        existing = next(
            (
                row
                for row in projects
                if isinstance(row, dict) and row.get("project_key") == config.project_key
            ),
            None,
        )
    assert isinstance(existing, dict)
    assert existing.get("enabled") is True
    assert str(existing.get("schema_name") or "").strip()
    return existing


def test_codex_oauth_model_registered_tool_persists_and_reads_back_material() -> None:
    """Exercise the user API through the real model and the registered write owner."""

    config = _live_config()
    marker = f"live-host-{time.time_ns()}"
    title = f"LIVE HOST MATERIAL {marker}"
    body_marker = f"Persistent material marker: {marker}."
    prompt = (
        "Execute one bounded MRW live-host acceptance task. Use the registered "
        "writing.document.create tool exactly once to create a persisted writing material. "
        f"Use the exact title {json.dumps(title)} and ensure body_md contains the exact sentence "
        f"{json.dumps(body_marker)}. Set source_refs to [\"live-host:{marker}\"] and provenance "
        f"to {{\"origin\": \"codex-oauth-live-host\", \"marker\": \"{marker}\"}}. "
        "Do not use dry_run, shell commands, filesystem writes, or any alternate persistence path. "
        "When the tool asks for approval, wait for the host. After creation succeeds, call "
        "writing.document.read with the returned doc_id and then report the exact doc_id and title."
    )

    project = _ensure_project(config)
    account = _webui(config, "GET", "/api/account")
    assert isinstance(account, dict)
    assert (account.get("account") or {}).get("type") == "chatgpt"
    models = _webui(config, "GET", "/api/models?limit=50")
    model_ids = {
        str(row.get("id") or "")
        for row in (models.get("data", []) if isinstance(models, dict) else [])
        if isinstance(row, dict)
    }
    assert config.model in model_ids

    started = _webui(
        config,
        "POST",
        "/api/threads",
        body={
            "model": config.model,
            "cwd": "/Users/wangyiliang/market-research-workflow",
            "mrwProjectKey": config.project_key,
        },
    )
    thread = started.get("thread") if isinstance(started, dict) else None
    assert isinstance(thread, dict) and thread.get("id")
    thread_id = str(thread["id"])

    turn_started = _webui(
        config,
        "POST",
        f"/api/threads/{quote(thread_id, safe='')}/turns",
        body={
            "input": [{"type": "text", "text": prompt}],
            "model": config.model,
            "effort": "low",
        },
    )
    turn = turn_started.get("turn") if isinstance(turn_started, dict) else None
    assert isinstance(turn, dict) and turn.get("id")
    turn_id = str(turn["id"])

    try:
        approved_action, terminal_turn = _wait_for_approved_turn(
            config,
            thread_id=thread_id,
            turn_id=turn_id,
            title=title,
            marker=body_marker,
        )
    except Exception:
        _interrupt_nonterminal_turn(config, thread_id=thread_id, turn_id=turn_id)
        raise
    items = _webui(
        config,
        "GET",
        f"/api/threads/{quote(thread_id, safe='')}/turns/{quote(turn_id, safe='')}/items",
    )
    assert title in json.dumps(items, ensure_ascii=False)

    from app.models.base import SessionLocal
    from app.models.entities import AgentApproval, AgentEvent, AgentMessage, AgentSession
    from app.models.writing_entities import WritingDocument
    from app.services.projects import bind_project
    from app.services.projects.context import bind_schema

    with SessionLocal() as session, bind_schema("public"):
        agent_session = session.execute(
            select(AgentSession).where(
                AgentSession.project_key == config.project_key,
                AgentSession.metadata_json["native_thread_id"].as_string() == thread_id,
            )
        ).scalar_one()
        messages = session.execute(
            select(AgentMessage).where(AgentMessage.session_id == agent_session.session_id)
        ).scalars().all()
        events = session.execute(
            select(AgentEvent).where(AgentEvent.session_id == agent_session.session_id)
        ).scalars().all()
        approval = session.execute(
            select(AgentApproval).where(
                AgentApproval.approval_id == str(approved_action["actionId"])
            )
        ).scalar_one()

        assert agent_session.source == "codex_webui_host"
        assert agent_session.entrypoint_type == "codex_native_thread"
        assert agent_session.metadata_json.get("native_thread_id") == thread_id
        assert any(
            row.role == "user"
            and row.content == prompt
            and (row.metadata_json or {}).get("host_message", {}).get("turn_id") == turn_id
            for row in messages
        )
        completed_create_events = [
            row
            for row in events
            if row.event_type == "macro_host.tool.dispatched"
            and (row.payload or {}).get("thread_id") == thread_id
            and (row.payload or {}).get("turn_id") == turn_id
            and (row.payload or {}).get("tool") == "writing.document.create"
            and (row.payload or {}).get("status") == "completed"
        ]
        assert len(completed_create_events) == 1
        create_event = completed_create_events[0]
        doc_id = int((create_event.payload or {})["structured_content"]["doc_id"])
        completed_read_events = [
            row
            for row in events
            if row.event_type == "macro_host.tool.dispatched"
            and (row.payload or {}).get("thread_id") == thread_id
            and (row.payload or {}).get("turn_id") == turn_id
            and (row.payload or {}).get("tool") == "writing.document.read"
            and (row.payload or {}).get("status") == "completed"
            and int(
                ((row.payload or {}).get("structured_content") or {}).get("document", {}).get("id")
                or 0
            )
            == doc_id
        ]
        assert completed_read_events
        assert approval.status == "consumed"
        assert approval.requester_session_id == agent_session.session_id

    api_document = _backend_document(config, doc_id)
    assert api_document["project_key"] == config.project_key
    assert api_document["title"] == title
    assert body_marker in api_document["body_md"]
    assert api_document["metadata_json"]["created_by"] == "agent_core"
    assert api_document["metadata_json"]["agent_core_call_id"] == create_event.payload["call_id"]
    assert api_document["metadata_json"]["source_refs"] == [f"live-host:{marker}"]
    assert api_document["metadata_json"]["provenance"]["marker"] == marker

    with SessionLocal() as session, bind_project(config.project_key):
        db_document = session.execute(
            select(WritingDocument).where(WritingDocument.id == doc_id)
        ).scalar_one()
        assert db_document.project_key == config.project_key
        assert db_document.title == title
        assert db_document.body_md == api_document["body_md"]
        assert db_document.metadata_json == api_document["metadata_json"]

    print(
        "LIVE_HOST_MATERIAL_CHAIN="
        + json.dumps(
            {
                "status": "passed",
                "model": config.model,
                "project_key": config.project_key,
                "project_schema": project["schema_name"],
                "thread_id": thread_id,
                "turn_id": turn_id,
                "turn_status": terminal_turn["status"],
                "session_id": agent_session.session_id,
                "call_id": create_event.payload["call_id"],
                "approval_id": approved_action["actionId"],
                "approval_status": approval.status,
                "doc_id": doc_id,
                "title": title,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
