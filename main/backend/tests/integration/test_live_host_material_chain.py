from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import select


pytestmark = pytest.mark.integration


_TERMINAL_TURN_STATES = {"completed", "failed", "interrupted"}


@dataclass(frozen=True)
class _LiveHostConfig:
    webui_url: str
    webui_api_key: str = field(repr=False)
    backend_url: str
    project_key: str
    model: str
    timeout_seconds: int


@dataclass(frozen=True)
class _LiveUrlWorkerConfig:
    host: _LiveHostConfig
    fixture_url: str
    fixture_marker: str
    public_fixture: bool


def _required_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        pytest.fail(f"{name} is required when MRW_LIVE_HOST_MATERIAL_CHAIN=1")
    return value


def _live_config(*, opt_in: str = "MRW_LIVE_HOST_MATERIAL_CHAIN") -> _LiveHostConfig:
    if os.getenv(opt_in) != "1":
        pytest.skip(f"real Codex OAuth/model calls require {opt_in}=1")
    return _LiveHostConfig(
        webui_url=_required_env("MRW_LIVE_HOST_WEBUI_URL").rstrip("/"),
        webui_api_key=_required_env("MRW_LIVE_HOST_WEBUI_API_KEY"),
        backend_url=_required_env("MRW_LIVE_HOST_BACKEND_URL").rstrip("/"),
        project_key=_required_env("MRW_LIVE_HOST_PROJECT_KEY"),
        model=str(os.getenv("MRW_LIVE_HOST_MODEL") or "gpt-6-luna").strip(),
        timeout_seconds=max(60, int(os.getenv("MRW_LIVE_HOST_TIMEOUT_SECONDS") or "300")),
    )


def _live_url_worker_config() -> _LiveUrlWorkerConfig:
    host = _live_config(opt_in="MRW_LIVE_HOST_URL_WORKER_CHAIN")
    fixture_url = _required_env("MRW_LIVE_HOST_URL_FIXTURE_URL")
    parsed = urlsplit(fixture_url)
    public_fixture = os.getenv("MRW_LIVE_HOST_URL_PUBLIC_FIXTURE") == "1"
    if public_fixture:
        if parsed.scheme != "https" or not parsed.hostname:
            pytest.fail(
                "MRW_LIVE_HOST_URL_FIXTURE_URL must be one exact HTTPS URL when "
                "MRW_LIVE_HOST_URL_PUBLIC_FIXTURE=1"
            )
    elif parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        pytest.fail("MRW_LIVE_HOST_URL_FIXTURE_URL must be one exact loopback HTTP URL")
    return _LiveUrlWorkerConfig(
        host=host,
        fixture_url=fixture_url,
        fixture_marker=_required_env("MRW_LIVE_HOST_URL_FIXTURE_MARKER"),
        public_fixture=public_fixture,
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


def _wait_for_url_submit_turn(
    config: _LiveUrlWorkerConfig,
    *,
    thread_id: str,
    turn_id: str,
    idempotency_key: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Await one exact registered async URL submission, with approval when required."""

    deadline = time.monotonic() + config.host.timeout_seconds
    approved_action: dict[str, Any] | None = None
    terminal_turn: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        pending = _webui(
            config.host,
            "GET",
            f"/api/mrw/pending?threadId={quote(thread_id, safe='')}",
        )
        if isinstance(pending, list) and pending:
            assert approved_action is None, "the bounded URL turn requested more than one approval"
            assert len(pending) == 1, f"expected one pending action, received {len(pending)}"
            action = pending[0]
            assert action.get("threadId") == thread_id
            assert action.get("turnId") == turn_id
            assert action.get("toolName") == "ingest.url_pool.submit"
            arguments = action.get("arguments") or {}
            assert arguments.get("project_key") == config.host.project_key
            assert arguments.get("url") == config.fixture_url
            assert arguments.get("async_mode") is True
            assert arguments.get("idempotency_key") == idempotency_key
            _webui(
                config.host,
                "POST",
                "/api/mrw/confirm",
                body={
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "actionId": action["actionId"],
                    "approved": True,
                    "userText": "Approve this exact bounded URL ingestion submission.",
                },
            )
            approved_action = action

        turn = _find_turn(config.host, thread_id, turn_id)
        if turn is not None and str(turn.get("status") or "") in _TERMINAL_TURN_STATES:
            terminal_turn = turn
            break
        time.sleep(1)

    assert terminal_turn is not None, (
        "the URL submission turn did not reach a terminal state; "
        f"approval_observed={approved_action is not None}"
    )
    assert terminal_turn.get("status") == "completed", terminal_turn.get("error")
    return approved_action, terminal_turn


def _wait_for_terminal_turn(
    config: _LiveHostConfig,
    *,
    thread_id: str,
    turn_id: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + config.timeout_seconds
    while time.monotonic() < deadline:
        turn = _find_turn(config, thread_id, turn_id)
        if turn is not None and str(turn.get("status") or "") in _TERMINAL_TURN_STATES:
            assert turn.get("status") == "completed", turn.get("error")
            return turn
        time.sleep(1)
    raise AssertionError("the bounded live-host turn did not reach a terminal state")


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


def test_codex_oauth_model_url_submit_reaches_independent_worker_and_document() -> None:
    """Drive one registered URL submission through Redis, a worker, Runtime, and Document."""

    config = _live_url_worker_config()
    host = config.host
    marker = f"live-url-worker-{time.time_ns()}"
    idempotency_key = f"live-url-worker:{marker}"
    query_terms = (
        [config.fixture_marker]
        if config.public_fixture
        else ["local release worker acceptance"]
    )
    source_name = (
        "Authorized Public URL Worker Fixture"
        if config.public_fixture
        else "Local Release URL Worker Fixture"
    )
    prompt = (
        "Execute one bounded MRW URL-worker acceptance task. Call the registered "
        "ingest.url_pool.submit tool exactly once with project_key "
        f"{json.dumps(host.project_key)}, url {json.dumps(config.fixture_url)}, "
        f"query_terms {json.dumps(query_terms)}, strict_mode false, "
        f"async_mode true, source_name {json.dumps(source_name)}, "
        f"idempotency_key {json.dumps(idempotency_key)}, and metadata "
        f"{{\"fixture_marker\": {json.dumps(config.fixture_marker)}, "
        "\"origin\": \"codex-oauth-url-worker\"}}. Do not call a synchronous ingest, "
        "shell, filesystem, writing.document.create, or any alternate persistence path. "
        "When the registered tool asks for approval, wait for the host. After the submission "
        "returns, report its exact runtime_run_ref and stop without calling ingest.url_pool.status."
    )

    project = _ensure_project(host)
    account = _webui(host, "GET", "/api/account")
    assert isinstance(account, dict)
    assert (account.get("account") or {}).get("type") == "chatgpt"
    models = _webui(host, "GET", "/api/models?limit=50")
    model_ids = {
        str(row.get("id") or "")
        for row in (models.get("data", []) if isinstance(models, dict) else [])
        if isinstance(row, dict)
    }
    assert host.model in model_ids

    started = _webui(
        host,
        "POST",
        "/api/threads",
        body={
            "model": host.model,
            "cwd": "/Users/wangyiliang/market-research-workflow",
            "mrwProjectKey": host.project_key,
        },
    )
    thread = started.get("thread") if isinstance(started, dict) else None
    assert isinstance(thread, dict) and thread.get("id")
    thread_id = str(thread["id"])
    turn_started = _webui(
        host,
        "POST",
        f"/api/threads/{quote(thread_id, safe='')}/turns",
        body={
            "input": [{"type": "text", "text": prompt}],
            "model": host.model,
            "effort": "low",
        },
    )
    turn = turn_started.get("turn") if isinstance(turn_started, dict) else None
    assert isinstance(turn, dict) and turn.get("id")
    submit_turn_id = str(turn["id"])
    try:
        approved_action, submit_turn = _wait_for_url_submit_turn(
            config,
            thread_id=thread_id,
            turn_id=submit_turn_id,
            idempotency_key=idempotency_key,
        )
    except Exception:
        _interrupt_nonterminal_turn(host, thread_id=thread_id, turn_id=submit_turn_id)
        raise

    from app.models.base import SessionLocal, engine
    from app.models.entities import AgentApproval, AgentEvent, AgentSession, Document
    from app.services.projects import bind_project
    from app.services.projects.context import bind_schema
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES

    with SessionLocal() as session, bind_schema("public"):
        agent_session = session.execute(
            select(AgentSession).where(
                AgentSession.project_key == host.project_key,
                AgentSession.metadata_json["native_thread_id"].as_string() == thread_id,
            )
        ).scalar_one()
        submit_events = [
            row
            for row in session.execute(
                select(AgentEvent).where(AgentEvent.session_id == agent_session.session_id)
            ).scalars()
            if row.event_type == "macro_host.tool.dispatched"
            and (row.payload or {}).get("thread_id") == thread_id
            and (row.payload or {}).get("turn_id") == submit_turn_id
            and (row.payload or {}).get("tool") == "ingest.url_pool.submit"
            and (row.payload or {}).get("status") == "completed"
        ]
        assert len(submit_events) == 1
        submit_event = submit_events[0]
        submit_content = (submit_event.payload or {}).get("structured_content") or {}
        assert isinstance(submit_content, dict)
        runtime_run_ref = str(submit_content.get("runtime_run_ref") or "")
        assert runtime_run_ref.startswith("runtime-run:")
        run_id = runtime_run_ref.removeprefix("runtime-run:")
        work_item_ids = [str(item) for item in submit_content.get("work_item_ids") or []]
        assert work_item_ids
        approval = None
        if approved_action is not None:
            approval = session.execute(
                select(AgentApproval).where(
                    AgentApproval.approval_id == str(approved_action["actionId"])
                )
            ).scalar_one()
            assert approval.status == "consumed"
            assert approval.requester_session_id == agent_session.session_id
        else:
            pending = _webui(
                host,
                "GET",
                f"/api/mrw/pending?threadId={quote(thread_id, safe='')}",
            )
            assert pending == []

    deadline = time.monotonic() + host.timeout_seconds
    run_row: dict[str, Any] | None = None
    work_rows: list[dict[str, Any]] = []
    attempt_rows: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            run_mapping = connection.execute(
                select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.project_key == host.project_key,
                    PUBLIC_TABLES["runtime_runs"].c.run_id == run_id,
                )
            ).mappings().one_or_none()
            run_row = dict(run_mapping) if run_mapping is not None else None
            work_rows = [
                dict(row)
                for row in connection.execute(
                    select(PUBLIC_TABLES["runtime_work_items"]).where(
                        PUBLIC_TABLES["runtime_work_items"].c.project_key == host.project_key,
                        PUBLIC_TABLES["runtime_work_items"].c.run_id == run_id,
                    )
                ).mappings()
            ]
            attempt_rows = [
                dict(row)
                for row in connection.execute(
                    select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                        PUBLIC_TABLES["runtime_effect_attempts"].c.project_key == host.project_key,
                        PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == run_id,
                    )
                ).mappings()
            ]
        if run_row is not None and run_row.get("state") in {
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "SUPERSEDED",
        }:
            break
        time.sleep(1)

    assert run_row is not None
    assert run_row["state"] == "COMPLETED", run_row
    submitted_work = {
        str(row["work_item_id"]): row
        for row in work_rows
        if str(row["work_item_id"]) in work_item_ids
    }
    assert set(submitted_work) == set(work_item_ids), work_rows
    assert all(row["state"] == "COMPLETED" for row in submitted_work.values()), submitted_work
    assert all(int(row["attempt_count"]) >= 1 for row in submitted_work.values()), submitted_work
    submitted_step_ids = {str(row["step_id"]) for row in submitted_work.values()}
    submitted_attempts = [
        row for row in attempt_rows if str(row["step_id"]) in submitted_step_ids
    ]
    assert submitted_attempts
    assert all(row["disposition"] == "SUCCEEDED" for row in submitted_attempts), submitted_attempts

    status_prompt = (
        "The canonical worker run has now terminated. Call the registered "
        "ingest.url_pool.status tool exactly once with project_key "
        f"{json.dumps(host.project_key)} and url {json.dumps(config.fixture_url)}. "
        "Do not submit another URL and do not call any write tool. Report verified, pending, "
        "runtime_run_ref, runtime output status, and document_id exactly as returned."
    )
    status_started = _webui(
        host,
        "POST",
        f"/api/threads/{quote(thread_id, safe='')}/turns",
        body={
            "input": [{"type": "text", "text": status_prompt}],
            "model": host.model,
            "effort": "low",
        },
    )
    status_turn = status_started.get("turn") if isinstance(status_started, dict) else None
    assert isinstance(status_turn, dict) and status_turn.get("id")
    status_turn_id = str(status_turn["id"])
    try:
        terminal_status_turn = _wait_for_terminal_turn(
            host,
            thread_id=thread_id,
            turn_id=status_turn_id,
        )
    except Exception:
        _interrupt_nonterminal_turn(host, thread_id=thread_id, turn_id=status_turn_id)
        raise
    pending = _webui(
        host,
        "GET",
        f"/api/mrw/pending?threadId={quote(thread_id, safe='')}",
    )
    assert pending == []

    with SessionLocal() as session, bind_schema("public"):
        status_events = [
            row
            for row in session.execute(
                select(AgentEvent).where(AgentEvent.session_id == agent_session.session_id)
            ).scalars()
            if row.event_type == "macro_host.tool.dispatched"
            and (row.payload or {}).get("thread_id") == thread_id
            and (row.payload or {}).get("turn_id") == status_turn_id
            and (row.payload or {}).get("tool") == "ingest.url_pool.status"
            and (row.payload or {}).get("status") == "completed"
        ]
        assert len(status_events) == 1
        status_event = status_events[0]
        status_content = (status_event.payload or {}).get("structured_content") or {}
        assert isinstance(status_content, dict)
        assert status_content.get("verified") is True
        assert status_content.get("pending") is False
        assert status_content.get("runtime_run_ref") == runtime_run_ref
        runtime_output = status_content.get("runtime_output") or {}
        assert isinstance(runtime_output, dict)
        assert runtime_output.get("status") == "completed"
        document_id = runtime_output.get("document_id")
        assert isinstance(document_id, int) and document_id > 0
        document_readback = status_content.get("document_readback") or {}
        assert isinstance(document_readback, dict)
        assert int(document_readback.get("document_id") or 0) == document_id

    api_response = _json_request(
        "GET",
        (
            f"{host.backend_url}/api/v1/admin/materials/{document_id}"
            f"?project_key={quote(host.project_key, safe='')}"
        ),
    )
    assert isinstance(api_response, dict) and api_response.get("status") == "ok", api_response
    api_document = api_response.get("data")
    assert isinstance(api_document, dict)
    assert api_document.get("uri") == config.fixture_url
    assert config.fixture_marker in json.dumps(api_document, ensure_ascii=False, default=str)

    with SessionLocal() as session, bind_project(host.project_key):
        db_document = session.execute(
            select(Document).where(Document.id == document_id)
        ).scalar_one()
        assert db_document.uri == config.fixture_url
        assert config.fixture_marker in json.dumps(
            {
                "title": db_document.title,
                "content": db_document.content,
                "summary": db_document.summary,
                "extracted_data": db_document.extracted_data,
            },
            ensure_ascii=False,
            default=str,
        )

    print(
        "LIVE_HOST_URL_WORKER_CHAIN="
        + json.dumps(
            {
                "status": "passed",
                "model": host.model,
                "project_key": host.project_key,
                "project_schema": project["schema_name"],
                "thread_id": thread_id,
                "submit_turn_id": submit_turn_id,
                "submit_turn_status": submit_turn["status"],
                "status_turn_id": status_turn_id,
                "status_turn_status": terminal_status_turn["status"],
                "session_id": agent_session.session_id,
                "submit_call_id": submit_event.payload["call_id"],
                "status_call_id": status_event.payload["call_id"],
                "approval_id": (
                    approved_action["actionId"] if approved_action is not None else None
                ),
                "approval_status": approval.status if approval is not None else "preauthorized",
                "runtime_run_ref": runtime_run_ref,
                "work_item_ids": work_item_ids,
                "document_id": document_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
